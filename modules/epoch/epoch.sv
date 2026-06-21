// EPOCH: Real-time clock synthesizer
// Divides 25 MHz sys_clk to 1 Hz. Maintains seconds, minutes, hours, days.
// Resets on power loss. Settable by CPU.
//
// Memory map:
//   0x000: SECONDS (read/write) — 0-59
//   0x004: MINUTES (read/write) — 0-59
//   0x008: HOURS   (read/write) — 0-23
//   0x00C: DAYS    (read/write) — 0-65535
//   0x010: CONTROL (write) — bit 0 = enable, bit 1 = reset to 00:00:00
//   0x014: TICKS   (read)  — sub-second tick counter (0-24999999)
//   0x018: UPTIME  (read)  — total seconds since last reset (32-bit)

module epoch #(
    parameter integer CLK_HZ = 25000000
) (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [24:0] tick;    // 0 to CLK_HZ-1
    logic [5:0]  sec;     // 0-59
    logic [5:0]  min;     // 0-59
    logic [4:0]  hour;    // 0-23
    logic [15:0] day;
    logic        enabled;
    logic [31:0] uptime;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            tick    <= 25'd0;
            sec     <= 6'd0;
            min     <= 6'd0;
            hour    <= 5'd0;
            day     <= 16'd0;
            enabled <= 1'b0;
            uptime  <= 32'd0;
        end else begin
            // 1 Hz tick
            if (enabled) begin
                if (tick >= CLK_HZ - 1) begin
                    tick <= 25'd0;
                    uptime <= uptime + 32'd1;
                    if (sec == 6'd59) begin
                        sec <= 6'd0;
                        if (min == 6'd59) begin
                            min <= 6'd0;
                            if (hour == 5'd23) begin
                                hour <= 5'd0;
                                day <= day + 16'd1;
                            end else
                                hour <= hour + 5'd1;
                        end else
                            min <= min + 6'd1;
                    end else
                        sec <= sec + 6'd1;
                end else
                    tick <= tick + 25'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: sec  <= reg_wdata[5:0];
                    3'h1: min  <= reg_wdata[5:0];
                    3'h2: hour <= reg_wdata[4:0];
                    3'h3: day  <= reg_wdata[15:0];
                    3'h4: begin
                        enabled <= reg_wdata[0];
                        if (reg_wdata[1]) begin
                            tick <= 25'd0; sec <= 6'd0; min <= 6'd0;
                            hour <= 5'd0; day <= 16'd0; uptime <= 32'd0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {26'd0, sec};
                    3'h1: reg_rdata <= {26'd0, min};
                    3'h2: reg_rdata <= {27'd0, hour};
                    3'h3: reg_rdata <= {16'd0, day};
                    3'h4: reg_rdata <= {31'd0, enabled};
                    3'h5: reg_rdata <= {7'd0, tick};
                    3'h6: reg_rdata <= uptime;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
