// GLYPH: Galois Logic for Yielding Polynomial Hashes
// Single-cycle GF(2^8) arithmetic unit using AES polynomial x^8+x^4+x^3+x+1 (0x11B).
//
// Memory map:
//   0x000: OP_A   (write) — 8-bit operand A
//   0x004: OP_B   (write) — 8-bit operand B
//   0x008: MUL    (read)  — GF multiply A*B
//   0x00C: INV    (read)  — GF multiplicative inverse of A
//   0x010: EXP    (read)  — GF exponentiation A^B (repeated multiplication)
//   0x014: CONTROL (write) — bit 0 = start EXP computation
//   0x018: STATUS  (read)  — bit 0 = EXP done

module glyph (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0] op_a, op_b;

    // GF(2^8) multiplication: polynomial reduction modulo 0x11B
    function automatic [7:0] gf_mul(input [7:0] a, input [7:0] b);
        logic [7:0] result;
        logic [7:0] aa;
        integer i;
        result = 8'd0;
        aa = a;
        for (i = 0; i < 8; i = i + 1) begin
            if (b[i]) result = result ^ aa;
            if (aa[7]) aa = (aa << 1) ^ 8'h1B;
            else       aa = aa << 1;
        end
        gf_mul = result;
    endfunction

    // Combinational multiply
    wire [7:0] mul_result = gf_mul(op_a, op_b);

    // GF inverse via lookup (Fermat's little theorem: a^254 = a^{-1} in GF(2^8))
    // Compute iteratively: too expensive combinationally for 254 multiplies.
    // Use a small FSM for EXP and INV.

    logic [7:0] exp_result;
    logic [7:0] exp_acc;
    logic [7:0] exp_cnt;
    logic       exp_running;
    logic       exp_done;
    logic       exp_is_inv;  // if true, computing a^254 for inverse

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            op_a       <= 8'd0;
            op_b       <= 8'd0;
            exp_result <= 8'd0;
            exp_acc    <= 8'd1;
            exp_cnt    <= 8'd0;
            exp_running <= 1'b0;
            exp_done   <= 1'b0;
            exp_is_inv <= 1'b0;
        end else begin
            if (exp_running) begin
                if (exp_cnt == 8'd0) begin
                    exp_result  <= exp_acc;
                    exp_running <= 1'b0;
                    exp_done    <= 1'b1;
                end else begin
                    exp_acc <= gf_mul(exp_acc, op_a);
                    exp_cnt <= exp_cnt - 8'd1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: op_a <= reg_wdata[7:0];
                    3'h1: op_b <= reg_wdata[7:0];
                    3'h5: begin // CONTROL
                        if (reg_wdata[0]) begin // start EXP (A^B)
                            exp_running <= 1'b1;
                            exp_done    <= 1'b0;
                            exp_acc     <= 8'd1;
                            exp_cnt     <= op_b;
                            exp_is_inv  <= 1'b0;
                        end
                        if (reg_wdata[1]) begin // start INV (A^254)
                            exp_running <= 1'b1;
                            exp_done    <= 1'b0;
                            exp_acc     <= 8'd1;
                            exp_cnt     <= 8'd254;
                            exp_is_inv  <= 1'b1;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {24'd0, op_a};
                    3'h1: reg_rdata <= {24'd0, op_b};
                    3'h2: reg_rdata <= {24'd0, mul_result};
                    3'h3: reg_rdata <= {24'd0, exp_result};  // INV or EXP result
                    3'h4: reg_rdata <= {24'd0, exp_result};  // EXP result
                    3'h5: reg_rdata <= 32'd0;
                    3'h6: reg_rdata <= {31'd0, exp_done};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
