// HEDGE: Hardware token bucket rate limiter
// Programmable rate (tokens per tick), burst depth.
// Returns allow/deny per request. Tick is every 256 clocks.
//
// Memory map:
//   0x000: REQUEST  (write) — consume one token, read RESULT after
//   0x004: RESULT   (read)  — bit 0 = last request allowed (1) or denied (0)
//   0x008: CONTROL  (write) — bit 0 = enable, bit 1 = reset
//   0x00C: RATE     (write) — tokens added per tick (0-255)
//   0x010: BURST    (write) — max token bucket depth
//   0x014: TOKENS   (read)  — current token count
//   0x018: ALLOWED  (read)  — total allowed requests since reset
//   0x01C: DENIED   (read)  — total denied requests since reset

module hedge (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [15:0] tokens;
    logic [15:0] burst_max;
    logic [7:0]  rate;
    logic        enabled;
    logic        last_allowed;
    logic [7:0]  prescaler;
    logic [31:0] allowed_count;
    logic [31:0] denied_count;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            tokens        <= 16'd0;
            burst_max     <= 16'd100;
            rate          <= 8'd1;
            enabled       <= 1'b0;
            last_allowed  <= 1'b0;
            prescaler     <= 8'd0;
            allowed_count <= 32'd0;
            denied_count  <= 32'd0;
        end else begin
            // Token replenishment tick
            if (enabled) begin
                prescaler <= prescaler + 8'd1;
                if (prescaler == 8'd255) begin
                    if (tokens + {8'd0, rate} > burst_max)
                        tokens <= burst_max;
                    else
                        tokens <= tokens + {8'd0, rate};
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin // REQUEST
                        if (tokens > 16'd0) begin
                            tokens <= tokens - 16'd1;
                            last_allowed <= 1'b1;
                            allowed_count <= allowed_count + 32'd1;
                        end else begin
                            last_allowed <= 1'b0;
                            denied_count <= denied_count + 32'd1;
                        end
                    end
                    3'h2: begin // CONTROL
                        enabled <= reg_wdata[0];
                        if (reg_wdata[1]) begin
                            tokens <= 16'd0;
                            allowed_count <= 32'd0;
                            denied_count <= 32'd0;
                            last_allowed <= 1'b0;
                        end
                    end
                    3'h3: rate <= reg_wdata[7:0];
                    3'h4: begin
                        burst_max <= reg_wdata[15:0];
                        tokens <= reg_wdata[15:0]; // fill to max on set
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {31'd0, last_allowed};
                    3'h5: reg_rdata <= {16'd0, tokens};
                    3'h6: reg_rdata <= allowed_count;
                    3'h7: reg_rdata <= denied_count;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
