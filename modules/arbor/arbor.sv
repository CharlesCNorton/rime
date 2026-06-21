// ARBOR: Priority interrupt controller
// 16 interrupt sources, 16-bit mask, priority encoder selects highest-numbered
// unmasked pending source. Software writes to RAISE to set a pending bit;
// CLAIM atomically reads the highest pending source and clears it.
//
// Memory map:
//   0x000: PENDING (read/write) — 16-bit pending bitmap (write-1-to-set)
//   0x004: MASK    (write/read) — 16-bit mask (1 = enabled, 0 = masked)
//   0x008: CLAIM   (read)       — top pending source ID + clear, returns 16 if none
//   0x00C: ANY     (read)       — bit 0 = any pending && unmasked
//   0x010: CONTROL (write)      — bit 0 = clear all pending
//   0x014: RAISE   (write)      — write source ID (0..15) to set that pending bit

module arbor (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [15:0] pending;
    logic [15:0] mask;

    wire [15:0] active = pending & mask;

    // Priority encoder: highest-numbered active bit (encoded MSB-first)
    logic [4:0] top_src;
    always_comb begin
        top_src = 5'd16;
        for (integer i = 0; i < 16; i = i + 1) begin
            if (active[i]) top_src = i[4:0];
        end
    end

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            pending <= 16'd0;
            mask    <= 16'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: pending <= pending | reg_wdata[15:0];
                    3'h1: mask    <= reg_wdata[15:0];
                    3'h4: begin
                        if (reg_wdata[0]) pending <= 16'd0;
                    end
                    3'h5: begin
                        if (reg_wdata[3:0] != 4'hF || reg_wdata[4] == 1'b0)
                            pending[reg_wdata[3:0]] <= 1'b1;
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {16'd0, pending};
                    3'h1: reg_rdata <= {16'd0, mask};
                    3'h2: begin
                        reg_rdata <= {27'd0, top_src};
                        if (top_src != 5'd16) pending[top_src[3:0]] <= 1'b0;
                    end
                    3'h3: reg_rdata <= {31'd0, |active};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
