// CRANK: Cyclic Register Arithmetic Numerical Kernel
// 32x32 -> 64-bit unsigned iterative multiplier. 32 cycles per multiply.
// Shift-and-add: tests each bit of operand B, conditionally adds A
// shifted to the corresponding position.
//
// Memory map:
//   0x000: OP_A     (write) — 32-bit operand A
//   0x004: OP_B     (write) — 32-bit operand B; triggers computation
//   0x008: RESULT_LO (read) — low 32 bits of product
//   0x00C: RESULT_HI (read) — high 32 bits of product
//   0x010: STATUS    (read) — bit 0 = done
//   0x014: CONTROL   (write) — bit 0 = reset

module crank (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] op_a;
    logic [31:0] op_b_shift;
    logic [63:0] accumulator;
    logic [63:0] a_shifted;
    logic [5:0]  bit_idx;
    logic        computing;
    logic        done;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            op_a        <= 32'd0;
            op_b_shift  <= 32'd0;
            accumulator <= 64'd0;
            a_shifted   <= 64'd0;
            bit_idx     <= 6'd0;
            computing   <= 1'b0;
            done        <= 1'b0;
        end else begin
            if (computing) begin
                if (op_b_shift[0])
                    accumulator <= accumulator + a_shifted;
                a_shifted  <= {a_shifted[62:0], 1'b0};
                op_b_shift <= {1'b0, op_b_shift[31:1]};
                if (bit_idx == 6'd31) begin
                    computing <= 1'b0;
                    done      <= 1'b1;
                end
                bit_idx <= bit_idx + 6'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        op_a <= reg_wdata;
                    end
                    3'h1: begin
                        op_b_shift  <= reg_wdata;
                        a_shifted   <= {32'd0, op_a};
                        accumulator <= 64'd0;
                        bit_idx     <= 6'd0;
                        computing   <= 1'b1;
                        done        <= 1'b0;
                    end
                    3'h5: begin
                        if (reg_wdata[0]) begin
                            op_a        <= 32'd0;
                            op_b_shift  <= 32'd0;
                            accumulator <= 64'd0;
                            a_shifted   <= 64'd0;
                            computing   <= 1'b0;
                            done        <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= op_a;
                    3'h1: reg_rdata <= 32'd0;
                    3'h2: reg_rdata <= accumulator[31:0];
                    3'h3: reg_rdata <= accumulator[63:32];
                    3'h4: reg_rdata <= {31'd0, done};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
