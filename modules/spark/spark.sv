// SPARK: Simple Perceptron with Activation and Responsive Kernel
// 8-input single-layer perceptron with signed 8-bit weights.
// Computes: sum = Σ(input[i] * weight[i]) + bias, then applies
// step activation: output = (sum >= 0) ? 1 : 0.
// Iterative multiply-accumulate: 8 cycles after trigger.
//
// Memory map:
//   0x000-0x01C: INPUT[0..7]  (write) — signed 8-bit inputs
//   0x020-0x03C: WEIGHT[0..7] (write) — signed 8-bit weights
//   0x040:       BIAS          (write) — signed 16-bit bias
//   0x044:       CONTROL       (write) — bit 0 = compute, bit 1 = reset
//   0x048:       STATUS        (read)  — bit 0 = done
//   0x04C:       SUM           (read)  — signed 32-bit weighted sum + bias
//   0x050:       OUTPUT        (read)  — 0 or 1 (step activation)

module spark (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic signed [7:0]  inputs  [0:7];
    logic signed [7:0]  weights [0:7];
    logic signed [15:0] bias;
    logic signed [31:0] accum;
    logic [3:0]  step;
    logic        computing;
    logic        done;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            for (integer i = 0; i < 8; i = i + 1) begin
                inputs[i]  <= 8'sd0;
                weights[i] <= 8'sd0;
            end
            bias      <= 16'sd0;
            accum     <= 32'sd0;
            step      <= 4'd0;
            computing <= 1'b0;
            done      <= 1'b0;
        end else begin
            if (computing) begin
                if (step < 4'd8) begin
                    accum <= accum + (inputs[step[2:0]] * weights[step[2:0]]);
                    step  <= step + 4'd1;
                end
                if (step == 4'd8) begin
                    accum     <= accum + {{16{bias[15]}}, bias};
                    computing <= 1'b0;
                    done      <= 1'b1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b0)
                    inputs[reg_addr[4:2]] <= reg_wdata[7:0];
                else if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b1)
                    weights[reg_addr[4:2]] <= reg_wdata[7:0];
                else case (reg_addr[6:2])
                    5'h10: bias <= reg_wdata[15:0];
                    5'h11: begin
                        if (reg_wdata[1]) begin
                            accum <= 32'sd0;
                            done  <= 1'b0;
                        end
                        if (reg_wdata[0]) begin
                            accum     <= 32'sd0;
                            step      <= 4'd0;
                            computing <= 1'b1;
                            done      <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[6:2])
                    5'h12: reg_rdata <= {31'd0, done};
                    5'h13: reg_rdata <= accum;
                    5'h14: reg_rdata <= {31'd0, ~accum[31]};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
