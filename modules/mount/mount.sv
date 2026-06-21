// MOUNT: Modular Operation Utility for Number Theory
// 256-bit iterative Montgomery multiplier.
// Computes A * B * R^-1 mod M where R = 2^256.
// 256 cycles per multiply. Operands loaded via 8 x 32-bit writes.
//
// Memory map:
//   0x000-0x01C: A[0..7]      (write) — 256-bit operand A (little-endian words)
//   0x020-0x03C: B[0..7]      (write) — 256-bit operand B
//   0x040-0x05C: M[0..7]      (write) — 256-bit modulus (must be odd)
//   0x060:       CONTROL       (write) — bit 0 = start
//   0x064:       STATUS        (read)  — bit 0 = done
//   0x080-0x09C: RESULT[0..7]  (read)  — 256-bit result

module mount (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    logic [255:0] a_reg, b_reg, m_reg;
    logic [256:0] acc;  // 257 bits for overflow during add
    logic [8:0]   bit_idx;
    logic         computing, done;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            a_reg <= 256'd0; b_reg <= 256'd0; m_reg <= 256'd1;
            acc <= 257'd0; bit_idx <= 9'd0;
            computing <= 1'b0; done <= 1'b0;
        end else begin
            if (computing) begin
                // Montgomery reduction: one bit of A per cycle
                // if A[bit_idx] == 1: acc += B
                // if acc[0] == 1: acc += M
                // acc >>= 1
                if (bit_idx < 9'd256) begin
                    logic [256:0] t;
                    t = acc;
                    if (a_reg[bit_idx[7:0]])
                        t = t + {1'b0, b_reg};
                    if (t[0])
                        t = t + {1'b0, m_reg};
                    acc <= t >> 1;
                    bit_idx <= bit_idx + 9'd1;
                end else begin
                    // Final reduction: if acc >= M, subtract M
                    if (acc >= {1'b0, m_reg})
                        acc <= acc - {1'b0, m_reg};
                    computing <= 1'b0;
                    done <= 1'b1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:8] == 4'h0) begin
                    case (reg_addr[7:5])
                        3'b000: a_reg[reg_addr[4:2]*32 +: 32] <= reg_wdata;
                        3'b001: b_reg[reg_addr[4:2]*32 +: 32] <= reg_wdata;
                        3'b010: m_reg[reg_addr[4:2]*32 +: 32] <= reg_wdata;
                        3'b011: begin
                            if (reg_addr[4:2] == 3'h0 && reg_wdata[0]) begin
                                acc <= 257'd0;
                                bit_idx <= 9'd0;
                                computing <= 1'b1;
                                done <= 1'b0;
                            end
                        end
                    endcase
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[7:5] == 3'b011 && reg_addr[4:2] == 3'h1)
                    reg_rdata <= {31'd0, done};
                else if (reg_addr[7:5] == 3'b100)
                    reg_rdata <= acc[reg_addr[4:2]*32 +: 32];
                else
                    reg_rdata <= 32'd0;
            end
        end
    end
endmodule
