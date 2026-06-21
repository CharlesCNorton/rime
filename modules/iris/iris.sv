// IRIS: Introspective Register Inspection System.
//
// Polymorphic DMA-driven data sampler for the RIME compositor. Autonomously
// reads registers from any composed module via a dedicated bus-master port.
// The CPU configures a sample list; IRIS cycles through it at hardware speed,
// writing results to a BRAM ring buffer. The host reads frames via the
// standard register interface.
//
// IRIS is the first non-CPU bus master in the compositor. When present,
// compose.py generates a priority bus arbiter: CPU wins ties, IRIS reads
// in gaps between CPU transactions.
//
// DMA port (active bus master — directly drives the module bus):
//   dma_addr[31:0]  — target register address (module region 0x30-0x3F)
//   dma_rd          — read strobe
//   dma_rdata[31:0] — returned data
//   dma_ready       — transaction complete
//
// Register map (CPU-side, standard compositor interface):
//   0x000  STATUS      (R)  [0]running [1]buffer_half [2]buffer_full [3]overflow
//   0x004  CONTROL     (W)  [0]start/stop [1]single_shot [2]clear_buffer
//   0x008  SAMPLE_CNT  (R)  total DMA reads completed [31:0]
//   0x00C  FRAME_CNT   (R)  complete frames captured [31:0]
//   0x010  LIST_LEN    (W)  number of active sample-list entries (1-16)
//   0x014  LIST_RATE   (W)  cycles between sample-list sweeps [31:0]
//   0x018  BUF_RD      (R)  next sample from ring buffer (auto-advance)
//   0x01C  BUF_LEVEL   (R)  samples available in ring buffer [10:0]
//   0x020  MANIFEST    (R)  composition manifest word (auto-advance through 16 entries)
//
//   0x100-0x13C  SAMPLE_LIST[0..15]  (W) target address for each sample slot
//   0x140-0x17C  SAMPLE_TAG[0..15]   (W) metadata tag per slot (module_id, register_id, type)
//
// Frame format in ring buffer (per sample-list sweep):
//   [FRAME_MAGIC] [frame_number] [timestamp_lo] [timestamp_hi]
//   [sample_0] [sample_1] ... [sample_N-1]
//
// The manifest (readable at 0x020) contains one 32-bit word per composed
// module: [7:0]=address_nibble, [15:8]=module_type, [31:16]=lut_count.
// Written by compose.py into the firmware init. IRIS reads it at boot
// to self-describe the composition to the host.

module iris (
    input  wire        clk,
    input  wire        rst,

    // Standard compositor register interface (CPU access)
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready,

    // DMA bus master port (active — IRIS initiates reads)
    output logic [31:0] dma_addr,
    output logic        dma_rd,
    input  wire  [31:0] dma_rdata,
    input  wire         dma_ready
);

    localparam integer BUF_DEPTH = 1024;  // 1 DP16KD at 32-bit width
    localparam integer MAX_SLOTS = 16;
    localparam integer FRAME_MAGIC = 32'h49524953;  // "IRIS"

    // --- Sample list ---
    logic [31:0] sample_addr [0:MAX_SLOTS-1];
    logic [31:0] sample_tag  [0:MAX_SLOTS-1];
    logic [4:0]  list_len;
    logic [31:0] list_rate;

    // --- Ring buffer (BRAM) ---
    (* ram_style = "block" *)
    reg [31:0] ring_buf [0:BUF_DEPTH-1];
    logic [9:0]  buf_wr, buf_rd_ptr;
    logic [10:0] buf_level;
    logic        buf_overflow;

    // --- State ---
    logic        running;
    logic        single_shot;
    logic [31:0] rate_counter;
    logic [4:0]  slot_idx;
    logic [31:0] sample_count;
    logic [31:0] frame_count;
    logic [31:0] timestamp;
    logic [3:0]  manifest_rd_idx;

    // Write acknowledgement: set by DMA FSM block, read by register block.
    logic wr_ack;

    // --- DMA FSM ---
    localparam [2:0] D_IDLE    = 3'd0;
    localparam [2:0] D_HEADER  = 3'd1;
    localparam [2:0] D_REQUEST = 3'd2;
    localparam [2:0] D_WAIT    = 3'd3;
    localparam [2:0] D_STORE   = 3'd4;
    localparam [2:0] D_ADVANCE = 3'd5;
    localparam [2:0] D_DONE    = 3'd6;

    logic [2:0] dma_state;
    logic [31:0] dma_result;
    logic [1:0]  hdr_phase;

    // --- Timestamp counter ---
    always_ff @(posedge clk) begin
        if (rst) timestamp <= 32'd0;
        else     timestamp <= timestamp + 32'd1;
    end

    // Buffer push signal: the DMA FSM sets buf_push_val and buf_push_en.
    // The buffer management always_ff block below handles the actual write.
    logic [31:0] buf_push_val;
    logic        buf_push_en;
    // Buffer pop signal: set by the register read path.
    logic        buf_pop;
    // Buffer clear signal: set by CONTROL register write.
    logic        buf_clear;

    always_ff @(posedge clk) begin
        if (rst || buf_clear) begin
            buf_wr <= 10'd0; buf_rd_ptr <= 10'd0;
            buf_level <= 11'd0; buf_overflow <= 1'b0;
        end else begin
            if (buf_push_en && buf_pop) begin
                ring_buf[buf_wr] <= buf_push_val;
                buf_wr <= buf_wr + 10'd1;
                buf_rd_ptr <= buf_rd_ptr + 10'd1;
            end else if (buf_push_en) begin
                ring_buf[buf_wr] <= buf_push_val;
                buf_wr <= buf_wr + 10'd1;
                if (buf_level < BUF_DEPTH)
                    buf_level <= buf_level + 11'd1;
                else
                    buf_overflow <= 1'b1;
            end else if (buf_pop && buf_level > 11'd0) begin
                buf_rd_ptr <= buf_rd_ptr + 10'd1;
                buf_level <= buf_level - 11'd1;
            end
        end
    end

    // --- DMA FSM ---
    always_ff @(posedge clk) begin
        dma_rd <= 1'b0;
        buf_push_en <= 1'b0;
        wr_ack <= 1'b0;

        if (rst) begin
            dma_state <= D_IDLE;
            dma_addr  <= 32'd0;
            running   <= 1'b0;
            single_shot <= 1'b0;
            slot_idx  <= 5'd0;
            rate_counter <= 32'd0;
            sample_count <= 32'd0;
            frame_count  <= 32'd0;
            list_len  <= 5'd0;
            list_rate <= 32'd25000;
            hdr_phase <= 2'd0;
            manifest_rd_idx <= 4'd0;
            for (int i = 0; i < MAX_SLOTS; i = i + 1) begin
                sample_addr[i] <= 32'd0;
                sample_tag[i]  <= 32'd0;
            end
        end else begin
            // Rate counter
            if (running) begin
                if (dma_state == D_IDLE) begin
                    if (rate_counter >= list_rate) begin
                        rate_counter <= 32'd0;
                        dma_state <= D_HEADER;
                        hdr_phase <= 2'd0;
                        slot_idx <= 5'd0;
                    end else
                        rate_counter <= rate_counter + 32'd1;
                end
            end

            case (dma_state)
                D_IDLE: begin
                    // Waiting for rate counter (handled above)
                end

                D_HEADER: begin
                    case (hdr_phase)
                        2'd0: begin buf_push_val<=FRAME_MAGIC; buf_push_en<=1; hdr_phase<=2'd1; end
                        2'd1: begin buf_push_val<=frame_count; buf_push_en<=1; hdr_phase<=2'd2; end
                        2'd2: begin buf_push_val<=timestamp;   buf_push_en<=1; hdr_phase<=2'd3; end
                        2'd3: begin
                            buf_push_val<={27'd0, list_len}; buf_push_en<=1;
                            dma_state<=(list_len>5'd0)?D_REQUEST:D_DONE;
                        end
                    endcase
                end

                D_REQUEST: begin
                    dma_addr <= sample_addr[slot_idx];
                    dma_rd   <= 1'b1;
                    dma_state <= D_WAIT;
                end

                D_WAIT: begin
                    if (dma_ready) begin
                        dma_result <= dma_rdata;
                        dma_state  <= D_STORE;
                    end
                end

                D_STORE: begin
                    buf_push_val <= dma_result; buf_push_en <= 1;
                    sample_count <= sample_count + 32'd1;
                    dma_state <= D_ADVANCE;
                end

                D_ADVANCE: begin
                    if (slot_idx + 5'd1 >= list_len)
                        dma_state <= D_DONE;
                    else begin
                        slot_idx <= slot_idx + 5'd1;
                        dma_state <= D_REQUEST;
                    end
                end

                D_DONE: begin
                    frame_count <= frame_count + 32'd1;
                    if (single_shot) running <= 1'b0;
                    dma_state <= D_IDLE;
                end

                default: dma_state <= D_IDLE;
            endcase

            // --- Register writes ---
            if (reg_wr) begin
                wr_ack <= 1'b1;
                case (reg_addr)
                    12'h004: begin
                        if (reg_wdata[0]) running <= ~running;
                        if (reg_wdata[1]) single_shot <= 1'b1;
                        if (reg_wdata[2]) buf_clear <= 1'b1;
                    end
                    12'h010: list_len <= reg_wdata[4:0];
                    12'h014: list_rate <= reg_wdata;
                    default: begin
                        // Sample list writes: 0x100-0x13C
                        if (reg_addr >= 12'h100 && reg_addr < 12'h140)
                            sample_addr[(reg_addr - 12'h100) >> 2] <= reg_wdata;
                        // Sample tag writes: 0x140-0x17C
                        if (reg_addr >= 12'h140 && reg_addr < 12'h180)
                            sample_tag[(reg_addr - 12'h140) >> 2] <= reg_wdata;
                    end
                endcase
            end
        end
    end

    // --- Register reads ---
    logic [31:0] buf_rd_data;
    always_ff @(posedge clk) begin
        buf_rd_data <= ring_buf[buf_rd_ptr];
    end

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        buf_pop <= 1'b0;
        buf_clear <= 1'b0;
        if (rst) begin
            reg_rdata <= 32'd0;
        end else if (wr_ack) begin
            reg_ready <= 1'b1;
            reg_rdata <= 32'd0;
        end else if (reg_rd) begin
            reg_ready <= 1'b1;
            case (reg_addr)
                12'h000: reg_rdata <= {28'd0, buf_overflow, buf_level > (BUF_DEPTH-1),
                                       buf_level > (BUF_DEPTH/2), running};
                12'h008: reg_rdata <= sample_count;
                12'h00C: reg_rdata <= frame_count;
                12'h010: reg_rdata <= {27'd0, list_len};
                12'h014: reg_rdata <= list_rate;
                12'h018: begin
                    reg_rdata <= buf_rd_data;
                    if (buf_level > 11'd0) buf_pop <= 1'b1;
                end
                12'h01C: reg_rdata <= {21'd0, buf_level};
                12'h020: begin
                    // Manifest: read from sample_tag array (populated by firmware at boot)
                    reg_rdata <= sample_tag[manifest_rd_idx];
                    manifest_rd_idx <= manifest_rd_idx + 4'd1;
                end
                default: begin
                    // Sample list reads: 0x100-0x13C
                    if (reg_addr >= 12'h100 && reg_addr < 12'h140)
                        reg_rdata <= sample_addr[(reg_addr - 12'h100) >> 2];
                    else if (reg_addr >= 12'h140 && reg_addr < 12'h180)
                        reg_rdata <= sample_tag[(reg_addr - 12'h140) >> 2];
                    else
                        reg_rdata <= 32'd0;
                end
            endcase
        end
    end

endmodule
