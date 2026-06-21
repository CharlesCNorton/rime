// DELTA: Byte-stream XOR differencing engine
// Computes byte-wise XOR between two streams (old and new).
// Counts changed bytes. Useful for firmware delta analysis.
//
// Memory map:
//   0x000: OLD_BYTE (write) — feed one byte from old stream
//   0x004: NEW_BYTE (write) — feed one byte from new stream, triggers diff
//   0x008: DIFF     (read)  — XOR of last old ^ new byte
//   0x00C: CHANGED  (read)  — total changed bytes (where XOR != 0)
//   0x010: TOTAL    (read)  — total bytes compared
//   0x014: CONTROL  (write) — bit 0 = reset counters
//   0x018: SAME     (read)  — total unchanged bytes (XOR == 0)

module delta (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0]  old_byte;
    logic [7:0]  diff_byte;
    logic [31:0] changed;
    logic [31:0] total;
    logic [31:0] same;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            old_byte  <= 8'd0;
            diff_byte <= 8'd0;
            changed   <= 32'd0;
            total     <= 32'd0;
            same      <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: old_byte <= reg_wdata[7:0];
                    3'h1: begin // NEW_BYTE: compute diff
                        diff_byte <= old_byte ^ reg_wdata[7:0];
                        total <= total + 32'd1;
                        if ((old_byte ^ reg_wdata[7:0]) != 8'd0)
                            changed <= changed + 32'd1;
                        else
                            same <= same + 32'd1;
                    end
                    3'h5: begin
                        if (reg_wdata[0]) begin
                            changed <= 32'd0; total <= 32'd0;
                            same <= 32'd0; diff_byte <= 8'd0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: reg_rdata <= {24'd0, diff_byte};
                    3'h3: reg_rdata <= changed;
                    3'h4: reg_rdata <= total;
                    3'h6: reg_rdata <= same;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
