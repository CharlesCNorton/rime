// FLUX: Hardware PID controller
// Fixed-point 16.16 arithmetic. Programmable Kp, Ki, Kd gains.
// Anti-windup clamp on integral term. Output clamped to ±32767.
//
// Memory map:
//   0x000: SETPOINT (write) — target value (signed 16-bit)
//   0x004: MEASURED (write) — current measurement (signed 16-bit), triggers one PID step
//   0x008: OUTPUT   (read)  — PID output (signed 16-bit, clamped)
//   0x00C: KP       (write) — proportional gain (8.8 fixed-point)
//   0x010: KI       (write) — integral gain (8.8 fixed-point)
//   0x014: KD       (write) — derivative gain (8.8 fixed-point)
//   0x018: CONTROL  (write) — bit 0 = reset integrator and state
//   0x01C: ERROR    (read)  — last error (setpoint - measured)

module flux (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic signed [15:0] setpoint;
    logic signed [15:0] measured;
    logic signed [15:0] kp, ki, kd;   // 8.8 fixed-point gains
    logic signed [15:0] error_val;
    logic signed [15:0] prev_error;
    logic signed [31:0] integral;
    logic signed [15:0] output_val;

    // Anti-windup clamp
    localparam signed [31:0] INT_MAX =  32'sd2097152;
    localparam signed [31:0] INT_MIN = -32'sd2097152;

    // Combinational PID computation
    wire signed [15:0] cur_error = setpoint - $signed(reg_wdata[15:0]);
    wire signed [31:0] p_term = (cur_error * kp) >>> 8;
    wire signed [31:0] raw_integral = integral + cur_error;
    wire signed [31:0] clamped_integral = (raw_integral > INT_MAX) ? INT_MAX :
                                          (raw_integral < INT_MIN) ? INT_MIN : raw_integral;
    wire signed [31:0] i_term = (clamped_integral * ki) >>> 8;
    wire signed [31:0] d_term = ((cur_error - prev_error) * kd) >>> 8;
    wire signed [31:0] pid_sum = p_term + i_term + d_term;
    wire signed [15:0] clamped_output = (pid_sum > 32'sd32767) ? 16'sd32767 :
                                        (pid_sum < -32'sd32768) ? -16'sd32768 : pid_sum[15:0];

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            setpoint   <= 16'sd0;
            measured   <= 16'sd0;
            kp         <= 16'sd256;   // 1.0
            ki         <= 16'sd0;
            kd         <= 16'sd0;
            error_val  <= 16'sd0;
            prev_error <= 16'sd0;
            integral   <= 32'sd0;
            output_val <= 16'sd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: setpoint <= reg_wdata[15:0];
                    3'h1: begin // MEASURED: triggers PID step
                        measured <= reg_wdata[15:0];
                        error_val <= setpoint - $signed(reg_wdata[15:0]);
                        prev_error <= setpoint - $signed(reg_wdata[15:0]);
                        integral <= clamped_integral;
                        output_val <= clamped_output;
                    end
                    3'h3: kp <= reg_wdata[15:0];
                    3'h4: ki <= reg_wdata[15:0];
                    3'h5: kd <= reg_wdata[15:0];
                    3'h6: begin // CONTROL
                        if (reg_wdata[0]) begin
                            integral   <= 32'sd0;
                            prev_error <= 16'sd0;
                            output_val <= 16'sd0;
                            error_val  <= 16'sd0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {{16{setpoint[15]}}, setpoint};
                    3'h2: reg_rdata <= {{16{output_val[15]}}, output_val};
                    3'h7: reg_rdata <= {{16{error_val[15]}}, error_val};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
