// EMBER compositor module: self-sustaining hardware TRNG with XOR topology rotation.
//
// 192 ring oscillators always on across three thermally isolated die quadrants.
// Entropy output selects which of 4 precomputed XOR topologies determines
// the ring-to-channel assignment. The topology change is purely digital —
// it alters which jitter correlations are sampled without changing the
// thermal field. Zero power signature, zero thermal transient on switch.
//
// Pipeline: 192 rings -> topology-selected XOR collapse (8 channels of 24) ->
//   3-path majority voting -> Von Neumann debiasing -> LFSR whitening ->
//   AES-128-CBC conditioning -> output FIFO -> register bus
//
// Topologies derived from thermal geometry experiment data:
//   0: concentric rectangles (best overall entropy metrics)
//   1: isolation radial (highest frequency diversity)
//   2: single hot row (cleanest thermal monopole)
//   3: opposing walls (two independent heat sources)
//
// Register map:
//   0x000  ENTROPY     (R)  conditioned byte (0xFFFFFFFF if empty)
//   0x004  STATUS      (R)  [0]warmed [1]aes_ready [2]apt_alarm [3]stuck [4]valid
//   0x008  RING_FREQ   (R)  ring 0 frequency count
//   0x00C  STUCK       (R)  per-channel stuck bitmap [7:0]
//   0x010  WARMUP      (R)  warmup timer
//   0x014  CONTROL     (W)  [0]soft_reset [2:1]topology_select
//   0x018  HEALTH      (R)  APT window count [9:0]
//   0x01C  TOPOLOGY    (R)  active topology [1:0], switch count [31:2]
//   0x020  ENT_COUNT   (R)  total conditioned bytes
//   0x024  RAW_BYTE    (R)  pre-AES whitened byte
//   0x028  AUTO_ROTATE (W)  [0]enable auto-rotation from entropy feedback
//   0x02C  ROTATE_INT  (W)  auto-rotation interval (conditioned bytes between switches)

module ember (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    localparam integer CLK_HZ = 25000000;
    localparam integer PATHS = 3;
    localparam integer RINGS_PER_PATH = 64;
    localparam integer NUM_CH = 8;
    localparam integer TOTAL_RINGS = PATHS * RINGS_PER_PATH;  // 192
    localparam integer RINGS_PER_CH = TOTAL_RINGS / NUM_CH;   // 24
    localparam integer RING_STAGES = 5;
    localparam integer WARMUP_CYCLES = CLK_HZ * 60;
    localparam integer FREQ_INTERVAL = CLK_HZ;
    localparam integer STUCK_THRESHOLD = 1024;
    localparam integer NUM_TOPOLOGIES = 4;

    // --- Ring oscillators (always on, no gating) ---
    wire [TOTAL_RINGS-1:0] ring_out;
    genvar ri;
    generate for (ri = 0; ri < TOTAL_RINGS; ri = ri + 1) begin : gen_ring
        (* keep *) wire [RING_STAGES:0] r;
        assign r[0] = r[RING_STAGES];
        genvar st;
        for (st = 0; st < RING_STAGES; st = st + 1) begin : gen_st
            (* keep *) LUT4 #(.INIT(16'h5555)) inv (
                .Z(r[st+1]), .A(r[st]), .B(1'b0), .C(1'b0), .D(1'b0)
            );
        end
        assign ring_out[ri] = r[1];
    end endgenerate

    logic [TOTAL_RINGS-1:0] ring_sampled;
    always_ff @(posedge clk) begin
        if (rst) ring_sampled <= {TOTAL_RINGS{1'b0}};
        else     ring_sampled <= ring_out;
    end

    // --- Active topology selection ---
    logic [1:0]  active_topo;
    logic [29:0] switch_count;
    logic        auto_rotate;
    logic [31:0] rotate_interval;
    logic [31:0] rotate_counter;

    // XOR topology masks: 4 topologies x 8 channels x 192-bit bitmasks.
    // Each mask selects which rings contribute to a channel via XOR reduction.
    // Generated from thermal geometry experiment data.
    `include "ember_topo_masks.svh"

    // --- Majority voting across rotated channel triples ---
    logic [NUM_CH-1:0] voted_bits;
    assign voted_bits[0] = (channel_bits[0]&channel_bits[3]) | (channel_bits[0]&channel_bits[5]) | (channel_bits[3]&channel_bits[5]);
    assign voted_bits[1] = (channel_bits[1]&channel_bits[4]) | (channel_bits[1]&channel_bits[6]) | (channel_bits[4]&channel_bits[6]);
    assign voted_bits[2] = (channel_bits[2]&channel_bits[5]) | (channel_bits[2]&channel_bits[7]) | (channel_bits[5]&channel_bits[7]);
    assign voted_bits[3] = (channel_bits[3]&channel_bits[6]) | (channel_bits[3]&channel_bits[0]) | (channel_bits[6]&channel_bits[0]);
    assign voted_bits[4] = (channel_bits[4]&channel_bits[7]) | (channel_bits[4]&channel_bits[1]) | (channel_bits[7]&channel_bits[1]);
    assign voted_bits[5] = (channel_bits[5]&channel_bits[0]) | (channel_bits[5]&channel_bits[2]) | (channel_bits[0]&channel_bits[2]);
    assign voted_bits[6] = (channel_bits[6]&channel_bits[1]) | (channel_bits[6]&channel_bits[3]) | (channel_bits[1]&channel_bits[3]);
    assign voted_bits[7] = (channel_bits[7]&channel_bits[2]) | (channel_bits[7]&channel_bits[4]) | (channel_bits[2]&channel_bits[4]);

    // --- Von Neumann debiasing ---
    logic [NUM_CH-1:0] prev_bits;
    logic              vn_phase;
    logic [NUM_CH-1:0] vn_valid;
    logic [NUM_CH-1:0] vn_bits;

    always_ff @(posedge clk) begin
        vn_valid <= {NUM_CH{1'b0}};
        if (rst) begin prev_bits <= {NUM_CH{1'b0}}; vn_phase <= 1'b0; end
        else begin
            if (!vn_phase) begin
                prev_bits <= voted_bits;
                vn_phase  <= 1'b1;
            end else begin
                vn_phase <= 1'b0;
                for (int c = 0; c < NUM_CH; c = c + 1) begin
                    if (prev_bits[c] != voted_bits[c]) begin
                        vn_valid[c] <= 1'b1;
                        vn_bits[c]  <= prev_bits[c];
                    end
                end
            end
        end
    end

    // --- Entropy byte collector ---
    logic [7:0]  ent_byte;
    logic [2:0]  ent_bit_idx;
    logic        ent_byte_ready;

    always_ff @(posedge clk) begin
        ent_byte_ready <= 1'b0;
        if (rst) ent_bit_idx <= 3'd0;
        else begin
            for (int c = 0; c < NUM_CH; c = c + 1) begin
                if (vn_valid[c] && !ent_byte_ready) begin
                    ent_byte[ent_bit_idx] <= vn_bits[c];
                    if (ent_bit_idx == 3'd7) begin
                        ent_byte_ready <= 1'b1;
                        ent_bit_idx <= 3'd0;
                    end else
                        ent_bit_idx <= ent_bit_idx + 3'd1;
                end
            end
        end
    end

    // --- LFSR whitening ---
    logic [31:0] lfsr;
    logic [1:0]  lfsr_seed_idx;
    logic        lfsr_seeded;
    logic [7:0]  whitened_byte;
    logic        whitened_ready;
    wire         lfsr_fb = lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0];

    always_ff @(posedge clk) begin
        whitened_ready <= 1'b0;
        if (rst) begin
            lfsr <= 32'd1; lfsr_seed_idx <= 2'd0; lfsr_seeded <= 1'b0;
        end else if (!lfsr_seeded && ent_byte_ready && warmed_up) begin
            case (lfsr_seed_idx)
                2'd0: lfsr[7:0]   <= ent_byte;
                2'd1: lfsr[15:8]  <= ent_byte;
                2'd2: lfsr[23:16] <= ent_byte;
                2'd3: begin lfsr[31:24] <= ent_byte; lfsr_seeded <= 1'b1; end
            endcase
            lfsr_seed_idx <= lfsr_seed_idx + 2'd1;
        end else if (lfsr_seeded) begin
            lfsr <= {lfsr[30:0], lfsr_fb};
            if (lfsr == 32'd0) lfsr <= 32'd1;
            if (ent_byte_ready) begin
                whitened_byte <= ent_byte ^ lfsr[7:0];
                whitened_ready <= 1'b1;
            end
        end
    end

    // --- AES-128-CBC conditioning ---
    logic [127:0] aes_plaintext, aes_key, aes_iv, aes_ciphertext;
    logic         aes_start, aes_done, aes_busy;
    logic [3:0]   aes_collect_idx, aes_key_idx, aes_out_idx;
    logic         aes_key_loaded, aes_out_valid;
    logic [7:0]   conditioned_byte;
    logic         conditioned_ready;

    aes128 AES (
        .clk(clk), .rst(rst),
        .start(aes_start), .plaintext(aes_plaintext ^ aes_iv),
        .key(aes_key),
        .done(aes_done), .busy(aes_busy), .ciphertext(aes_ciphertext)
    );

    always_ff @(posedge clk) begin
        aes_start <= 1'b0;
        conditioned_ready <= 1'b0;
        if (rst) begin
            aes_collect_idx <= 4'd0; aes_key_loaded <= 1'b0;
            aes_key_idx <= 4'd0; aes_iv <= 128'd0;
            aes_out_idx <= 4'd0; aes_out_valid <= 1'b0;
        end else if (!aes_key_loaded && whitened_ready && warmed_up) begin
            aes_key[aes_key_idx*8 +: 8] <= whitened_byte;
            if (aes_key_idx == 4'd15)
                aes_key_loaded <= 1'b1;
            else
                aes_key_idx <= aes_key_idx + 4'd1;
        end else if (aes_key_loaded && !aes_out_valid) begin
            if (whitened_ready && !aes_busy) begin
                aes_plaintext[aes_collect_idx*8 +: 8] <= whitened_byte;
                if (aes_collect_idx == 4'd15) begin
                    aes_start <= 1'b1;
                    aes_collect_idx <= 4'd0;
                end else
                    aes_collect_idx <= aes_collect_idx + 4'd1;
            end
            if (aes_done) begin
                aes_iv <= aes_ciphertext;
                aes_out_valid <= 1'b1;
                aes_out_idx <= 4'd0;
            end
        end else if (aes_out_valid) begin
            conditioned_byte <= aes_ciphertext[aes_out_idx*8 +: 8];
            conditioned_ready <= 1'b1;
            if (aes_out_idx == 4'd15)
                aes_out_valid <= 1'b0;
            else
                aes_out_idx <= aes_out_idx + 4'd1;
        end
    end

    // --- Output FIFO ---
    logic [7:0]  out_fifo [0:15];
    logic [3:0]  out_wr, out_rd;
    wire         out_empty = (out_wr == out_rd);
    wire         out_full  = ((out_wr + 4'd1) == out_rd);
    logic        fifo_pop;  // driven by register read block

    always_ff @(posedge clk) begin
        if (rst) begin
            out_wr <= 4'd0;
            out_rd <= 4'd0;
        end else begin
            if (conditioned_ready && !out_full) begin
                out_fifo[out_wr] <= conditioned_byte;
                out_wr <= out_wr + 4'd1;
            end
            if (fifo_pop && !out_empty)
                out_rd <= out_rd + 4'd1;
        end
    end

    // --- Auto-rotation: entropy-driven topology switching ---
    always_ff @(posedge clk) begin
        if (rst) begin
            active_topo <= 2'd0;
            switch_count <= 30'd0;
            auto_rotate <= 1'b0;
            rotate_interval <= 32'd1024;
            rotate_counter <= 32'd0;
        end else begin
            if (reg_wr && reg_addr == 12'h014) begin
                active_topo <= reg_wdata[2:1];
            end
            if (reg_wr && reg_addr == 12'h028) begin
                auto_rotate <= reg_wdata[0];
            end
            if (reg_wr && reg_addr == 12'h02C) begin
                rotate_interval <= reg_wdata;
            end
            // Self-sustaining feedback: after rotate_interval conditioned bytes,
            // use the last 2 entropy bits to select the next topology.
            if (auto_rotate && conditioned_ready) begin
                rotate_counter <= rotate_counter + 32'd1;
                if (rotate_counter >= rotate_interval) begin
                    rotate_counter <= 32'd0;
                    active_topo <= conditioned_byte[1:0];
                    switch_count <= switch_count + 30'd1;
                end
            end
        end
    end

    // --- NIST SP 800-90B Adaptive Proportion Test ---
    logic [7:0]  apt_ref;
    logic [9:0]  apt_count;
    logic [9:0]  apt_window_idx;
    logic        apt_alarm;

    always_ff @(posedge clk) begin
        if (rst) begin apt_count <= 10'd0; apt_window_idx <= 10'd0; apt_alarm <= 1'b0; end
        else if (conditioned_ready) begin
            if (apt_window_idx == 10'd0) begin
                apt_ref <= conditioned_byte;
                apt_count <= 10'd0;
                apt_window_idx <= 10'd1;
            end else begin
                if (conditioned_byte == apt_ref) apt_count <= apt_count + 10'd1;
                if (apt_count >= 10'd325) apt_alarm <= 1'b1;
                if (apt_window_idx == 10'd511) begin
                    apt_window_idx <= 10'd0;
                    if (apt_count < 10'd325) apt_alarm <= 1'b0;
                end else
                    apt_window_idx <= apt_window_idx + 10'd1;
            end
        end
    end

    // --- Warmup ---
    logic [31:0] warmup_timer;
    logic        warmed_up;

    always_ff @(posedge clk) begin
        if (rst) begin warmed_up <= 1'b0; warmup_timer <= 32'd0; end
        else if (!warmed_up) begin
            warmup_timer <= warmup_timer + 32'd1;
            if (warmup_timer >= WARMUP_CYCLES) warmed_up <= 1'b1;
        end
    end

    // --- Ring frequency counter ---
    logic ring_s0, ring_s1, ring_s2;
    wire  ring_edge = ring_s1 && !ring_s2;
    always_ff @(posedge clk) begin
        if (rst) begin ring_s0 <= 1'b0; ring_s1 <= 1'b0; ring_s2 <= 1'b0; end
        else begin ring_s0 <= ring_out[0]; ring_s1 <= ring_s0; ring_s2 <= ring_s1; end
    end

    logic [31:0] freq_count, freq_timer, freq_current;
    always_ff @(posedge clk) begin
        if (rst) begin freq_count <= 32'd0; freq_timer <= 32'd0; freq_current <= 32'd0; end
        else begin
            if (ring_edge) freq_count <= freq_count + 32'd1;
            freq_timer <= freq_timer + 32'd1;
            if (freq_timer >= FREQ_INTERVAL) begin
                freq_current <= freq_count;
                freq_count <= 32'd0;
                freq_timer <= 32'd0;
            end
        end
    end

    // --- Per-channel stuck detector ---
    logic [NUM_CH-1:0] ch_stuck;
    logic [NUM_CH-1:0] ch_last_bit;
    logic [9:0]        stuck_cnt [0:NUM_CH-1];

    always_ff @(posedge clk) begin
        if (rst) begin
            ch_stuck <= {NUM_CH{1'b0}};
            for (int c = 0; c < NUM_CH; c = c + 1) begin
                ch_last_bit[c] <= 1'b0; stuck_cnt[c] <= 10'd0;
            end
        end else begin
            for (int c = 0; c < NUM_CH; c = c + 1) begin
                if (vn_valid[c]) begin
                    if (vn_bits[c] == ch_last_bit[c]) begin
                        if (stuck_cnt[c] < STUCK_THRESHOLD) stuck_cnt[c] <= stuck_cnt[c] + 10'd1;
                        if (stuck_cnt[c] >= STUCK_THRESHOLD - 1) ch_stuck[c] <= 1'b1;
                    end else begin stuck_cnt[c] <= 10'd0; ch_stuck[c] <= 1'b0; end
                    ch_last_bit[c] <= vn_bits[c];
                end
            end
        end
    end

    // --- Entropy counter ---
    logic [31:0] entropy_count;
    always_ff @(posedge clk) begin
        if (rst) entropy_count <= 32'd0;
        else if (conditioned_ready) entropy_count <= entropy_count + 32'd1;
    end

    // --- Register interface ---
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        fifo_pop <= 1'b0;
        if (rst) begin
            reg_rdata <= 32'd0;
        end else if (reg_wr) begin
            reg_ready <= 1'b1;
            reg_rdata <= 32'd0;
        end else if (reg_rd) begin
            reg_ready <= 1'b1;
            case (reg_addr)
                12'h000: begin
                    if (!out_empty) begin
                        reg_rdata <= {24'd0, out_fifo[out_rd]};
                        fifo_pop <= 1'b1;
                    end else
                        reg_rdata <= 32'hFFFFFFFF;
                end
                12'h004: reg_rdata <= {27'd0, !out_empty, |ch_stuck, apt_alarm,
                                       aes_key_loaded & lfsr_seeded, warmed_up};
                12'h008: reg_rdata <= freq_current;
                12'h00C: reg_rdata <= {24'd0, ch_stuck};
                12'h010: reg_rdata <= warmup_timer;
                12'h018: reg_rdata <= {22'd0, apt_count};
                12'h01C: reg_rdata <= {switch_count, active_topo};
                12'h020: reg_rdata <= entropy_count;
                12'h024: reg_rdata <= {24'd0, whitened_byte};
                12'h028: reg_rdata <= {31'd0, auto_rotate};
                12'h02C: reg_rdata <= rotate_interval;
                default: reg_rdata <= 32'd0;
            endcase
        end
    end

endmodule
