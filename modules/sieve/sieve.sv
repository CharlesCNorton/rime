// SIEVE: Selective Indexed Extract and Variable Embed
// Configurable bit-field extract and deposit for 32-bit values.
// Write source, position, width, then read extracted or deposited result.
// All operations are single-cycle combinational.
//
// Memory map:
//   0x000: SOURCE   (write) — 32-bit source value
//   0x004: CONFIG   (write) — bits [4:0] = position, bits [12:8] = width (1-32)
//   0x008: EXTRACT  (read)  — extracted field: (source >> pos) & ((1 << width) - 1)
//   0x00C: TARGET   (write) — 32-bit target value for deposit
//   0x010: FIELD    (write) — field value to deposit
//   0x014: DEPOSIT  (read)  — target with field inserted: (target & ~mask) | ((field << pos) & mask)
//   0x018: MASK     (read)  — computed mask for current config
//   0x01C: CONTROL  (write) — bit 0 = reset

module sieve (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] source;
    logic [4:0]  pos;
    logic [5:0]  width;
    logic [31:0] target;
    logic [31:0] field;

    wire [5:0] safe_width = (width == 6'd0) ? 6'd1 : (width > 6'd32) ? 6'd32 : width;
    wire [31:0] mask_raw = (safe_width >= 6'd32) ? 32'hFFFFFFFF : ((32'd1 << safe_width) - 32'd1);
    wire [31:0] mask_positioned = mask_raw << pos;
    wire [31:0] extracted = (source >> pos) & mask_raw;
    wire [31:0] deposited = (target & ~mask_positioned) | ((field << pos) & mask_positioned);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            source <= 32'd0;
            pos    <= 5'd0;
            width  <= 6'd1;
            target <= 32'd0;
            field  <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: source <= reg_wdata;
                    3'h1: begin
                        pos   <= reg_wdata[4:0];
                        width <= reg_wdata[13:8];
                    end
                    3'h3: target <= reg_wdata;
                    3'h4: field  <= reg_wdata;
                    3'h7: begin
                        if (reg_wdata[0]) begin
                            source <= 32'd0;
                            pos    <= 5'd0;
                            width  <= 6'd1;
                            target <= 32'd0;
                            field  <= 32'd0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= source;
                    3'h1: reg_rdata <= {18'd0, width, 3'd0, pos};
                    3'h2: reg_rdata <= extracted;
                    3'h3: reg_rdata <= target;
                    3'h4: reg_rdata <= field;
                    3'h5: reg_rdata <= deposited;
                    3'h6: reg_rdata <= mask_positioned;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
