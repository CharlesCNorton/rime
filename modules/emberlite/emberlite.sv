// EMBER-LITE: Hardware entropy source
// 8 ring oscillators using (* keep *) LUT4 primitives to prevent
// synthesis optimization.  4 channels of 2 rings each, XOR-collapsed
// per channel, Von Neumann debiased.  Debiased bits are shifted
// into a 32-bit collection register.
//
// The entropy comes from physical jitter in the free-running ring
// oscillator frequencies — manufacturing variation and thermal noise
// make each ring's period slightly unpredictable on each cycle.
//
// Memory map:
//   0x000: RANDOM  (read) — 32-bit collected entropy (changes every 32 debias events)
//   0x004: BYTE    (read) — low 8 bits of current collection register
//   0x008: CONTROL (write) — bit 0 = reset collection state
//   0x00C: COUNT   (read) — total completed 32-bit words since reset
//   0x010: RAW     (read) — instantaneous raw ring XOR sample (4 bits, channels 0-3)

module emberlite (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    localparam integer NUM_RINGS = 8;
    localparam integer RING_STAGES = 5;
    localparam integer NUM_CH = 4;
    localparam integer RINGS_PER_CH = NUM_RINGS / NUM_CH;

    // ---- Ring oscillators ----
    wire [NUM_RINGS-1:0] ring_out;

    genvar ri, st;
    generate
        for (ri = 0; ri < NUM_RINGS; ri = ri + 1) begin : gen_ring
            // Feedback loop: chain[0] = chain[RING_STAGES] forms a ring.
            // LUT4 INIT=0x5555 implements a single inverter (NOT gate).
            // (* keep *) prevents synthesis optimizing the ring away.
            (* keep *) wire [RING_STAGES:0] chain;
            assign chain[0] = chain[RING_STAGES];
            for (st = 0; st < RING_STAGES; st = st + 1) begin : gen_inv
                (* keep *) LUT4 #(.INIT(16'h5555)) inv (
                    .Z(chain[st+1]), .A(chain[st]),
                    .B(1'b0), .C(1'b0), .D(1'b0)
                );
            end
            assign ring_out[ri] = chain[1];
        end
    endgenerate

    // ---- Sample and XOR-collapse per channel ----
    logic [NUM_RINGS-1:0] ring_sampled;
    always_ff @(posedge clk) begin
        if (rst) ring_sampled <= '0;
        else     ring_sampled <= ring_out;
    end

    wire [NUM_CH-1:0] raw_bits;
    genvar ch;
    generate
        for (ch = 0; ch < NUM_CH; ch = ch + 1) begin : gen_ch
            assign raw_bits[ch] = ring_sampled[ch*RINGS_PER_CH]
                                ^ ring_sampled[ch*RINGS_PER_CH + 1];
        end
    endgenerate

    // ---- Von Neumann debiaser per channel ----
    // Collects pairs of samples.  01 -> output 0, 10 -> output 1.
    // 00 and 11 are discarded.  Produces unbiased bits at ~1/4 rate.
    logic [NUM_CH-1:0] prev_raw;
    logic               vn_phase;
    logic [NUM_CH-1:0] vn_valid;
    logic [NUM_CH-1:0] vn_bits;

    always_ff @(posedge clk) begin
        vn_valid <= '0;
        if (rst) begin
            prev_raw <= '0;
            vn_phase <= 1'b0;
        end else begin
            if (!vn_phase) begin
                prev_raw <= raw_bits;
                vn_phase <= 1'b1;
            end else begin
                vn_phase <= 1'b0;
                for (integer i = 0; i < NUM_CH; i = i + 1) begin
                    if (prev_raw[i] != raw_bits[i]) begin
                        vn_valid[i] <= 1'b1;
                        vn_bits[i]  <= prev_raw[i];
                    end
                end
            end
        end
    end

    // ---- Collection shift register ----
    // Shifts in debiased bits from all channels.  When 32 bits are
    // collected, latches the result and increments the word counter.
    logic [31:0] shift_reg;
    logic [5:0]  bit_count;
    logic [31:0] random_word;
    logic        word_ready;
    logic [31:0] read_count;

    always_ff @(posedge clk) begin
        word_ready <= 1'b0;
        if (rst) begin
            shift_reg   <= 32'd0;
            bit_count   <= 6'd0;
            random_word <= 32'd0;
            read_count  <= 32'd0;
        end else begin
            for (integer i = 0; i < NUM_CH; i = i + 1) begin
                if (vn_valid[i] && bit_count < 6'd32) begin
                    shift_reg <= {shift_reg[30:0], vn_bits[i]};
                    bit_count <= bit_count + 6'd1;
                end
            end
            if (bit_count >= 6'd32) begin
                random_word <= shift_reg;
                bit_count   <= 6'd0;
                word_ready  <= 1'b1;
                read_count  <= read_count + 32'd1;
            end

            if (reg_wr && reg_addr[4:2] == 3'h2 && reg_wdata[0]) begin
                shift_reg  <= 32'd0;
                bit_count  <= 6'd0;
                read_count <= 32'd0;
            end
        end
    end

    // ---- Register interface ----
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (!rst) begin
            if (reg_wr) reg_ready <= 1'b1;
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= random_word;
                    3'h1: reg_rdata <= {24'd0, random_word[7:0]};
                    3'h3: reg_rdata <= read_count;
                    3'h4: reg_rdata <= {28'd0, raw_bits};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
