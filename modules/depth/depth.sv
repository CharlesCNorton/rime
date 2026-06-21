// DEPTH: Dynamic Execution Profile and Thread Height tracker
// Monitors bus writes to a configurable stack-pointer address region.
// Tracks min and max values written, plus a sample counter.
// Uses snoop to passively observe the bus.
//
// Memory map:
//   0x000: SP_BASE  (write) — base address to monitor (e.g. 0x00000FFC for stack top)
//   0x004: SP_MASK  (write) — address mask (match when (addr & mask) == (base & mask))
//   0x008: SP_MIN   (read)  — minimum SP value observed
//   0x00C: SP_MAX   (read)  — maximum SP value observed
//   0x010: SAMPLES  (read)  — number of SP writes observed
//   0x014: LAST_SP  (read)  — most recent SP value
//   0x018: CONTROL  (write) — bit 0 = reset, bit 1 = enable tracking

module depth (
    input  wire        clk,
    input  wire        rst,

    input  wire [31:0] snoop_addr,
    input  wire [3:0]  snoop_wstrb,
    input  wire        snoop_valid,
    input  wire        snoop_ready,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] sp_base;
    logic [31:0] sp_mask;
    logic [31:0] sp_min;
    logic [31:0] sp_max;
    logic [31:0] samples;
    logic [31:0] last_sp;
    logic        tracking;

    wire addr_match = ((snoop_addr & sp_mask) == (sp_base & sp_mask));

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            sp_base  <= 32'd0;
            sp_mask  <= 32'hFFFFFFFF;
            sp_min   <= 32'hFFFFFFFF;
            sp_max   <= 32'd0;
            samples  <= 32'd0;
            last_sp  <= 32'd0;
            tracking <= 1'b0;
        end else begin
            if (tracking && snoop_valid && snoop_ready && addr_match) begin
                last_sp <= snoop_addr;
                samples <= samples + 32'd1;
                if (snoop_addr < sp_min) sp_min <= snoop_addr;
                if (snoop_addr > sp_max) sp_max <= snoop_addr;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: sp_base <= reg_wdata;
                    3'h1: sp_mask <= reg_wdata;
                    3'h6: begin
                        if (reg_wdata[0]) begin
                            sp_min   <= 32'hFFFFFFFF;
                            sp_max   <= 32'd0;
                            samples  <= 32'd0;
                            last_sp  <= 32'd0;
                        end
                        tracking <= reg_wdata[1];
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= sp_base;
                    3'h1: reg_rdata <= sp_mask;
                    3'h2: reg_rdata <= sp_min;
                    3'h3: reg_rdata <= sp_max;
                    3'h4: reg_rdata <= samples;
                    3'h5: reg_rdata <= last_sp;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
