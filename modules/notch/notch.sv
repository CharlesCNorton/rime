// NOTCH: Noise-Opposing Transition and Contact Handler
// 8-channel debounce filter. Each channel has a configurable threshold
// counter. The output only changes when the input has been stable for
// THRESHOLD consecutive samples. Sampling rate is sys_clk / PRESCALE.
//
// Memory map:
//   0x000: RAW_IN    (write) — bits [7:0] = simulated raw input (for testing)
//   0x004: FILTERED  (read)  — bits [7:0] = debounced output
//   0x008: CHANGED   (read)  — bits [7:0] = channels that changed since last read (clears on read)
//   0x00C: PRESCALE  (write) — 16-bit sample prescaler (default 0 = every cycle)
//   0x010: THRESHOLD (write) — 8-bit stability count required (default 16)
//   0x014: CONTROL   (write) — bit 0 = reset

module notch (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0]  raw_in;
    logic [7:0]  filtered;
    logic [7:0]  changed;
    logic [15:0] prescale;
    logic [7:0]  threshold;
    logic [15:0] prescale_cnt;
    logic [7:0]  stable_cnt [0:7];
    logic [7:0]  prev_raw;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            raw_in       <= 8'd0;
            filtered     <= 8'd0;
            changed      <= 8'd0;
            prescale     <= 16'd0;
            threshold    <= 8'd16;
            prescale_cnt <= 16'd0;
            prev_raw     <= 8'd0;
            for (integer i = 0; i < 8; i = i + 1)
                stable_cnt[i] <= 8'd0;
        end else begin
            // Sample at prescaled rate
            if (prescale_cnt >= prescale) begin
                prescale_cnt <= 16'd0;
                prev_raw <= raw_in;
                for (integer i = 0; i < 8; i = i + 1) begin
                    if (raw_in[i] != filtered[i]) begin
                        if (raw_in[i] == prev_raw[i])
                            stable_cnt[i] <= stable_cnt[i] + 8'd1;
                        else
                            stable_cnt[i] <= 8'd0;
                        if (stable_cnt[i] >= threshold) begin
                            filtered[i]   <= raw_in[i];
                            changed[i]    <= 1'b1;
                            stable_cnt[i] <= 8'd0;
                        end
                    end else begin
                        stable_cnt[i] <= 8'd0;
                    end
                end
            end else begin
                prescale_cnt <= prescale_cnt + 16'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: raw_in    <= reg_wdata[7:0];
                    3'h3: prescale  <= reg_wdata[15:0];
                    3'h4: threshold <= reg_wdata[7:0];
                    3'h5: begin
                        if (reg_wdata[0]) begin
                            raw_in   <= 8'd0;
                            filtered <= 8'd0;
                            changed  <= 8'd0;
                            prev_raw <= 8'd0;
                            for (integer i = 0; i < 8; i = i + 1)
                                stable_cnt[i] <= 8'd0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {24'd0, raw_in};
                    3'h1: reg_rdata <= {24'd0, filtered};
                    3'h2: begin
                        reg_rdata <= {24'd0, changed};
                        changed   <= 8'd0;
                    end
                    3'h3: reg_rdata <= {16'd0, prescale};
                    3'h4: reg_rdata <= {24'd0, threshold};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
