// TAPER: Tapered Arithmetic Precision Evaluation Register
// Simplified 8-bit fixed-point math coprocessor with saturation.
// Demonstrates the compositor interface for a math accelerator.
//
// Memory map:
//   0x000: OP_A   (write) — signed 8-bit operand A (-128..127)
//   0x004: OP_B   (write) — signed 8-bit operand B
//   0x008: ADD    (read)  — saturating A + B
//   0x00C: MUL    (read)  — A * B (signed, lower 8 bits of 16-bit product)
//   0x010: MUL_HI (read)  — upper 8 bits of A * B
//   0x014: ABS_A  (read)  — |A|
//   0x018: MIN    (read)  — min(A, B)
//   0x01C: MAX    (read)  — max(A, B)

module taper (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic signed [7:0] op_a, op_b;

    // Saturating add
    wire signed [8:0] add_full = {op_a[7], op_a} + {op_b[7], op_b};
    wire signed [7:0] add_sat = (add_full > 9'sd127) ? 8'sd127 :
                                (add_full < -9'sd128) ? -8'sd128 :
                                add_full[7:0];

    // Signed multiply
    wire signed [15:0] mul_full = op_a * op_b;

    // Absolute value
    wire [7:0] abs_a = op_a[7] ? (-op_a) : op_a;

    // Min/Max
    wire signed [7:0] min_ab = (op_a < op_b) ? op_a : op_b;
    wire signed [7:0] max_ab = (op_a > op_b) ? op_a : op_b;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            op_a <= 8'sd0;
            op_b <= 8'sd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: op_a <= reg_wdata[7:0];
                    3'h1: op_b <= reg_wdata[7:0];
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {{24{op_a[7]}}, op_a};
                    3'h1: reg_rdata <= {{24{op_b[7]}}, op_b};
                    3'h2: reg_rdata <= {{24{add_sat[7]}}, add_sat};
                    3'h3: reg_rdata <= {{24{mul_full[7]}}, mul_full[7:0]};
                    3'h4: reg_rdata <= {{24{mul_full[15]}}, mul_full[15:8]};
                    3'h5: reg_rdata <= {24'd0, abs_a};
                    3'h6: reg_rdata <= {{24{min_ab[7]}}, min_ab};
                    3'h7: reg_rdata <= {{24{max_ab[7]}}, max_ab};
                endcase
            end
        end
    end
endmodule
