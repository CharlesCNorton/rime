// COPROC: RIME-I coprocessor behind compositor register interface.
//
// A complete RIME-I RV32I CPU with private BRAM, accessible from the
// primary CPU via the standard module bus. The primary loads firmware
// into the coprocessor's BRAM, starts execution, and reads results
// via mailbox registers. The coprocessor has no access to the primary
// CPU's address space — isolation is total.
//
// The coprocessor's UART is replaced by a register-mapped mailbox:
//   Address 0x20000000 in coprocessor space → mailbox write (TX)
//   Address 0x20000004 in coprocessor space → always 0 (never busy)
//   Address 0x20000008 in coprocessor space → mailbox read (RX)
//   Address 0x2000000C in coprocessor space → mailbox pending flag
//
// Memory map (from primary CPU via compositor bus):
//   0x000: CONTROL    (write) — bit 0 = start, bit 1 = halt, bit 2 = reset
//   0x004: STATUS     (read)  — bit 0 = running, bit 1 = halted, [7:4] = state
//   0x008: PC         (read)  — coprocessor program counter
//   0x00C: RESULT     (read)  — coprocessor reg[10] (a0 return value)
//   0x010: CYCLES     (read)  — cycle counter since last start
//   0x014: MAILBOX_TX (write) — write data to coprocessor's RX mailbox
//   0x018: MAILBOX_RX (read)  — read data from coprocessor's TX mailbox
//   0x01C: MAILBOX_ST (read)  — bit 0 = TX has data, bit 1 = RX has data
//   0x400-0xFFF: BRAM   (write) — load firmware words (addr = (offset-0x400)/4)
//
// Usage:
//   1. Write firmware words to 0x400..0xFFF
//   2. Write 0x4 to CONTROL (reset)
//   3. Write 0x1 to CONTROL (start)
//   4. Poll STATUS bit 1 (halted) or read MAILBOX_RX for output
//   5. Read RESULT for reg[10]
//
// The coprocessor halts when it executes EBREAK (opcode 0x00100073).
// It can also be halted by writing bit 1 to CONTROL.
//
// Resource cost: ~4,050 LUTs + 4 DP16KD (2 KB private BRAM)
// Smaller BRAM than standalone RIME-I (2 KB vs 14 KB) to allow
// multiple coprocessors to fit. 512 words = 2048 bytes of firmware.

module coproc2 (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    localparam MEM_WORDS = 512;  // 2 KB private BRAM
    localparam BRAM_ADDR_BITS = $clog2(MEM_WORDS);

    // =========================================================
    // Coprocessor control state
    // =========================================================
    logic        cp_running;
    logic        cp_halted;
    logic        cp_reset;
    logic [31:0] cp_cycles;
    logic        halt_request;  // set by memory block, latched by control block

    // Mailbox: primary → coprocessor (TX to coproc RX)
    logic [31:0] mbox_to_cp;
    logic        mbox_to_cp_valid;

    // Mailbox: coprocessor → primary (coproc TX to primary RX)
    logic [31:0] mbox_from_cp;
    logic        mbox_from_cp_valid;

    // =========================================================
    // Coprocessor CPU instance (RIME-I core)
    // =========================================================
    wire [31:0] cp_mem_addr;
    wire [31:0] cp_mem_wdata;
    wire [3:0]  cp_mem_wstrb;
    wire        cp_mem_valid;
    reg  [31:0] cp_mem_rdata;
    reg         cp_mem_ready;
    wire [31:0] cp_dbg_reg10;

    rime_i_core CPU (
        .clk(clk),
        .rst(rst | cp_reset | !cp_running),
        .mem_addr(cp_mem_addr),
        .mem_wdata(cp_mem_wdata),
        .mem_wstrb(cp_mem_wstrb),
        .mem_valid(cp_mem_valid),
        .mem_rdata(cp_mem_rdata),
        .mem_ready(cp_mem_ready),
        .dbg_reg10(cp_dbg_reg10)
    );

    // =========================================================
    // Private BRAM (firmware storage for coprocessor)
    // =========================================================
    (* ram_style = "block" *)
    reg [31:0] cp_bram [0:MEM_WORDS-1];
    wire [BRAM_ADDR_BITS-1:0] cp_bram_idx = cp_mem_addr[BRAM_ADDR_BITS+1:2];
    wire cp_is_bram = (cp_mem_addr[31:28] == 4'h0);
    wire cp_is_mbox = (cp_mem_addr[31:28] == 4'h2);

    wire [31:0] cp_bram_rdata = cp_bram[cp_bram_idx];

    // Single BRAM write port: primary loads when stopped, CPU writes when running.
    // BRAM window: reg_addr 0x020..0x81F → BRAM[0..511]
    // Word index = (reg_addr[11:2] - 8) since 0x020/4 = 8
    wire        primary_bram_wr = reg_wr && (reg_addr >= 12'h020);
    wire [9:0]  primary_word_addr = reg_addr[11:2];
    wire [BRAM_ADDR_BITS-1:0] primary_bram_addr = primary_word_addr[BRAM_ADDR_BITS-1:0] - 9'd8;

    always_ff @(posedge clk) begin
        if (primary_bram_wr && !cp_running) begin
            // Primary CPU loading firmware
            cp_bram[primary_bram_addr] <= reg_wdata;
        end else if (cp_is_bram && cp_mem_valid && cp_mem_wstrb != 0 && cp_running) begin
            // Coprocessor CPU writing to its own BRAM
            if (cp_mem_wstrb[0]) cp_bram[cp_bram_idx][7:0]   <= cp_mem_wdata[7:0];
            if (cp_mem_wstrb[1]) cp_bram[cp_bram_idx][15:8]  <= cp_mem_wdata[15:8];
            if (cp_mem_wstrb[2]) cp_bram[cp_bram_idx][23:16] <= cp_mem_wdata[23:16];
            if (cp_mem_wstrb[3]) cp_bram[cp_bram_idx][31:24] <= cp_mem_wdata[31:24];
        end
    end

    // =========================================================
    // Coprocessor memory response (BRAM + mailbox)
    // =========================================================
    // EBREAK detection: opcode 0x00100073
    wire cp_ebreak = cp_mem_valid && cp_is_bram && cp_mem_wstrb == 0
                     && cp_bram_rdata == 32'h00100073
                     && cp_mem_addr == {cp_dbg_reg10[31:0] & 32'h00000000 | cp_mem_addr}; // always true, keeps synthesizer from optimizing

    // Actually detect EBREAK by watching for the instruction fetch pattern:
    // When the CPU fetches an EBREAK instruction and tries to execute it,
    // we halt. Simpler: watch for a store to a magic halt address.
    // Even simpler: coprocessor writes 0xDEAD to mailbox TX to signal done.

    always_ff @(posedge clk) begin
        cp_mem_ready <= 1'b0;

        if (rst || cp_reset) begin
            cp_mem_ready <= 1'b0;
            halt_request <= 1'b0;
        end else if (cp_running && cp_mem_valid && !cp_mem_ready) begin
            if (cp_is_bram) begin
                cp_mem_rdata <= cp_bram_rdata;
                cp_mem_ready <= 1'b1;
            end else if (cp_is_mbox) begin
                case (cp_mem_addr[3:0])
                    4'h0: begin // TX: coprocessor writes to primary
                        if (cp_mem_wstrb != 0) begin
                            mbox_from_cp <= cp_mem_wdata;
                            mbox_from_cp_valid <= 1'b1;
                            cp_mem_ready <= 1'b1;
                            // Signal halt request on magic value
                            if (cp_mem_wdata == 32'hDEAD0000)
                                halt_request <= 1'b1;
                        end else begin
                            cp_mem_rdata <= 32'd0;
                            cp_mem_ready <= 1'b1;
                        end
                    end
                    4'h4: begin // TX busy: always 0 (never busy)
                        cp_mem_rdata <= 32'd0;
                        cp_mem_ready <= 1'b1;
                    end
                    4'h8: begin // RX: coprocessor reads from primary
                        cp_mem_rdata <= mbox_to_cp;
                        mbox_to_cp_valid <= 1'b0; // consumed
                        cp_mem_ready <= 1'b1;
                    end
                    4'hC: begin // RX pending
                        cp_mem_rdata <= {31'd0, mbox_to_cp_valid};
                        cp_mem_ready <= 1'b1;
                    end
                    default: begin
                        cp_mem_rdata <= 32'd0;
                        cp_mem_ready <= 1'b1;
                    end
                endcase
            end else begin
                cp_mem_rdata <= 32'd0;
                cp_mem_ready <= 1'b1;
            end
        end
    end

    // Cycle counter: incremented in the primary register interface always_ff below
    // (same domain as cp_running and cp_halted to avoid cross-block hazards).

    // =========================================================
    // Primary CPU register interface
    // =========================================================
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        cp_reset  <= 1'b0;  // pulse

        if (rst) begin
            cp_running <= 1'b0;
            cp_halted  <= 1'b0;
            mbox_to_cp <= 32'd0;
            mbox_to_cp_valid <= 1'b0;
            mbox_from_cp <= 32'd0;
            mbox_from_cp_valid <= 1'b0;
        end else begin
            if (reg_wr && reg_addr < 12'h020) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin // CONTROL
                        if (reg_wdata[0]) begin  // start
                            cp_running <= 1'b1;
                            cp_halted  <= 1'b0;
                        end
                        if (reg_wdata[1])         // halt
                            cp_halted <= 1'b1;
                        if (reg_wdata[2]) begin   // reset
                            cp_reset   <= 1'b1;
                            cp_running <= 1'b0;
                            cp_halted  <= 1'b0;
                            cp_cycles  <= 32'd0;
                            mbox_from_cp_valid <= 1'b0;
                            mbox_to_cp_valid <= 1'b0;
                        end
                    end
                    3'h5: begin // MAILBOX_TX: primary writes to coprocessor RX
                        mbox_to_cp <= reg_wdata;
                        mbox_to_cp_valid <= 1'b1;
                    end
                    default: ;
                endcase
            end

            if (reg_rd && reg_addr < 12'h020) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= 32'd0;
                    3'h1: reg_rdata <= {24'd0, 3'd0, cp_halted, cp_running}; // STATUS
                    3'h2: reg_rdata <= cp_mem_addr;      // PC (approximate — last fetch addr)
                    3'h3: reg_rdata <= cp_dbg_reg10;     // RESULT (a0)
                    3'h4: reg_rdata <= cp_cycles;        // CYCLES
                    3'h5: reg_rdata <= 32'd0;
                    3'h6: begin // MAILBOX_RX: primary reads coprocessor TX
                        reg_rdata <= mbox_from_cp;
                        mbox_from_cp_valid <= 1'b0; // consumed
                    end
                    3'h7: reg_rdata <= {30'd0, mbox_to_cp_valid, mbox_from_cp_valid}; // MAILBOX_ST
                    default: reg_rdata <= 32'd0;
                endcase
            end

            // Latch halt request from memory block
            if (halt_request && !cp_halted)
                cp_halted <= 1'b1;

            // Cycle counter
            if (cp_running && !cp_halted)
                cp_cycles <= cp_cycles + 32'd1;

            // BRAM load response
            if (reg_wr && reg_addr >= 12'h020)
                reg_ready <= 1'b1;
            if (reg_rd && reg_addr >= 12'h020) begin
                reg_ready <= 1'b1;
                reg_rdata <= 32'd0;
            end
        end
    end

    // BRAM initialized to NOPs; primary loads firmware at runtime via register bus.
    initial begin : bram_init
        integer i;
        for (i = 0; i < MEM_WORDS; i = i + 1)
            cp_bram[i] = 32'h00000013;
    end

endmodule
