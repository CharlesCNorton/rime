// LATCH: Hardware watchdog timer + event counter
// Watchdog: counts down from a programmable threshold. If it hits 0
// without being kicked, the EXPIRED flag latches. CPU must kick regularly.
// Event counter: counts write-pulses to the EVENT register.
//
// Memory map:
//   0x000: KICK     (write) — any write resets the watchdog countdown
//   0x004: STATUS   (read)  — bit 0 = expired, bit 1 = running
//   0x008: CONTROL  (write) — bit 0 = enable watchdog, bit 1 = clear expired, bit 2 = reset counter
//   0x00C: TIMEOUT  (write) — set watchdog countdown value (in clock cycles / 256)
//   0x010: REMAIN   (read)  — remaining countdown ticks
//   0x014: EVENT    (write) — increment event counter (any write)
//   0x018: ECOUNT   (read)  — event counter value
//   0x01C: ESTAMP   (read)  — countdown value at last event (timestamp)

module latch (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] timeout_val;
    logic [31:0] countdown;
    logic [7:0]  prescaler;
    logic        enabled;
    logic        expired;

    logic [31:0] event_count;
    logic [31:0] event_stamp;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            timeout_val <= 32'd0;
            countdown   <= 32'd0;
            prescaler   <= 8'd0;
            enabled     <= 1'b0;
            expired     <= 1'b0;
            event_count <= 32'd0;
            event_stamp <= 32'd0;
        end else begin
            // Watchdog tick (every 256 clocks)
            if (enabled && !expired) begin
                prescaler <= prescaler + 8'd1;
                if (prescaler == 8'd255) begin
                    if (countdown == 32'd0)
                        expired <= 1'b1;
                    else
                        countdown <= countdown - 32'd1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: countdown <= timeout_val;           // KICK
                    3'h2: begin                               // CONTROL
                        enabled <= reg_wdata[0];
                        if (reg_wdata[1]) expired <= 1'b0;
                        if (reg_wdata[2]) begin
                            event_count <= 32'd0;
                            event_stamp <= 32'd0;
                        end
                    end
                    3'h3: begin                               // TIMEOUT
                        timeout_val <= reg_wdata;
                        countdown   <= reg_wdata;
                    end
                    3'h5: begin                               // EVENT
                        event_count <= event_count + 32'd1;
                        event_stamp <= countdown;
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {30'd0, enabled, expired};
                    3'h4: reg_rdata <= countdown;
                    3'h6: reg_rdata <= event_count;
                    3'h7: reg_rdata <= event_stamp;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
