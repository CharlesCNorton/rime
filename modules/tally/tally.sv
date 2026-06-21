// TALLY: Triggered Accumulating Linear Logic sYnthesizer
// 4-channel multiply-accumulate. Each channel:
//   acc += (op_a[15:0] * op_b[15:0])  (16x16 -> 32-bit product, added to 32-bit accumulator)
// Product computed iteratively (16 cycles, shift-and-add). Channels are independent.
// Write A to stage the multiplicand and channel, write B to trigger.
//
// Memory map:
//   0x000: OP_A     (write) — bits [15:0] = multiplicand, bits [17:16] = channel select
//   0x004: OP_B     (write) — bits [15:0] = multiplier; triggers MAC on selected channel
//   0x008: ACC0     (read)  — channel 0 accumulator
//   0x00C: ACC1     (read)  — channel 1 accumulator
//   0x010: ACC2     (read)  — channel 2 accumulator
//   0x014: ACC3     (read)  — channel 3 accumulator
//   0x018: STATUS   (read)  — bit 0 = done (all channels idle)
//   0x01C: CONTROL  (write) — bit 0 = reset all channels

module tally (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] acc [0:3];

    logic [31:0] mul_a_shifted;
    logic [15:0] mul_b_remain;
    logic [31:0] mul_product;
    logic [1:0]  mul_ch;
    logic [4:0]  mul_step;
    logic        mul_active;

    logic [15:0] staged_a;
    logic [1:0]  staged_ch;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            acc[0]         <= 32'd0;
            acc[1]         <= 32'd0;
            acc[2]         <= 32'd0;
            acc[3]         <= 32'd0;
            mul_active     <= 1'b0;
            mul_step       <= 5'd0;
            mul_product    <= 32'd0;
            mul_a_shifted  <= 32'd0;
            mul_b_remain   <= 16'd0;
            mul_ch         <= 2'd0;
            staged_a       <= 16'd0;
            staged_ch      <= 2'd0;
        end else begin
            if (mul_active) begin
                if (mul_b_remain[0])
                    mul_product <= mul_product + mul_a_shifted;
                mul_a_shifted <= {mul_a_shifted[30:0], 1'b0};
                mul_b_remain  <= {1'b0, mul_b_remain[15:1]};
                if (mul_step == 5'd15) begin
                    acc[mul_ch] <= acc[mul_ch] + mul_product +
                                   (mul_b_remain[0] ? mul_a_shifted : 32'd0);
                    mul_active <= 1'b0;
                end
                mul_step <= mul_step + 5'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        staged_a  <= reg_wdata[15:0];
                        staged_ch <= reg_wdata[17:16];
                    end
                    3'h1: begin
                        mul_a_shifted <= {16'd0, staged_a};
                        mul_b_remain  <= reg_wdata[15:0];
                        mul_ch        <= staged_ch;
                        mul_product   <= 32'd0;
                        mul_step      <= 5'd0;
                        mul_active    <= 1'b1;
                    end
                    3'h7: begin
                        if (reg_wdata[0]) begin
                            acc[0]     <= 32'd0;
                            acc[1]     <= 32'd0;
                            acc[2]     <= 32'd0;
                            acc[3]     <= 32'd0;
                            mul_active <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: reg_rdata <= acc[0];
                    3'h3: reg_rdata <= acc[1];
                    3'h4: reg_rdata <= acc[2];
                    3'h5: reg_rdata <= acc[3];
                    3'h6: reg_rdata <= {31'd0, ~mul_active};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
