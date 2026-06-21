// PULSE: 4-channel 16-bit PWM generator
// Each channel has independent period and duty cycle.
// Output is high while counter < duty, low otherwise. Counter wraps at period.
//
// Memory map:
//   0x000: CH0_PERIOD (write/read) — 16-bit period
//   0x004: CH0_DUTY   (write/read) — 16-bit duty
//   0x008: CH1_PERIOD
//   0x00C: CH1_DUTY
//   0x010: CH2_PERIOD
//   0x014: CH2_DUTY
//   0x018: CH3_PERIOD
//   0x01C: CH3_DUTY
//   0x020: OUTPUT     (read)       — bits [3:0] = current PWM output per channel
//   0x024: CONTROL    (write)      — bit 0 = enable, bit 1 = reset all counters
//   0x028: COUNTER0   (read)       — current counter value of channel 0 (debug)

module pulse (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [15:0] period [0:3];
    logic [15:0] duty   [0:3];
    logic [15:0] counter [0:3];
    logic        enabled;
    logic [3:0]  out;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            for (integer i = 0; i < 4; i = i + 1) begin
                period[i]  <= 16'd0;
                duty[i]    <= 16'd0;
                counter[i] <= 16'd0;
            end
            enabled <= 1'b0;
            out     <= 4'd0;
        end else begin
            if (enabled) begin
                for (integer i = 0; i < 4; i = i + 1) begin
                    if (counter[i] >= period[i] - 16'd1)
                        counter[i] <= 16'd0;
                    else
                        counter[i] <= counter[i] + 16'd1;
                    out[i] <= (counter[i] < duty[i]) ? 1'b1 : 1'b0;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: period[0] <= reg_wdata[15:0];
                    4'h1: duty[0]   <= reg_wdata[15:0];
                    4'h2: period[1] <= reg_wdata[15:0];
                    4'h3: duty[1]   <= reg_wdata[15:0];
                    4'h4: period[2] <= reg_wdata[15:0];
                    4'h5: duty[2]   <= reg_wdata[15:0];
                    4'h6: period[3] <= reg_wdata[15:0];
                    4'h7: duty[3]   <= reg_wdata[15:0];
                    4'h9: begin
                        if (reg_wdata[1]) begin
                            for (integer i = 0; i < 4; i = i + 1)
                                counter[i] <= 16'd0;
                        end
                        enabled <= reg_wdata[0];
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: reg_rdata <= {16'd0, period[0]};
                    4'h1: reg_rdata <= {16'd0, duty[0]};
                    4'h2: reg_rdata <= {16'd0, period[1]};
                    4'h3: reg_rdata <= {16'd0, duty[1]};
                    4'h4: reg_rdata <= {16'd0, period[2]};
                    4'h5: reg_rdata <= {16'd0, duty[2]};
                    4'h6: reg_rdata <= {16'd0, period[3]};
                    4'h7: reg_rdata <= {16'd0, duty[3]};
                    4'h8: reg_rdata <= {28'd0, out};
                    4'hA: reg_rdata <= {16'd0, counter[0]};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
