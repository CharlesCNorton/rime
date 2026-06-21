// ORACLE: 256-entry 16-bit lookup table with linear interpolation
// CPU loads the table, then queries with a 16-bit input (8.8 fixed-point).
// Integer part selects the table entry, fractional part interpolates.
//
// Memory map:
//   0x000: QUERY  (write) — 16-bit input (8.8 fixed-point), result available immediately
//   0x004: RESULT (read)  — interpolated 16-bit output
//   0x008: CONTROL (write) — bit 0 = load mode (table writes go to entries)
//   0x400-0x7FF: TABLE[0..255] (write) — 16-bit entries

module oracle (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // 64-entry table (fits in LUT RAM). `table` is a reserved SystemVerilog
    // keyword, so the array is named `tbl`.
    logic [15:0] tbl [0:63];

    logic [15:0] query_val;
    logic [15:0] result_val;

    // Interpolation uses reg_wdata directly for combinational result
    wire [5:0] idx = reg_wdata[13:8];
    wire [7:0] frac = reg_wdata[7:0];
    wire [5:0] idx_next = (idx == 6'd63) ? 6'd63 : idx + 6'd1;

    wire [15:0] val_a = tbl[idx];
    wire [15:0] val_b = tbl[idx_next];

    // Linear interpolation: result = val_a + (val_b - val_a) * frac / 256
    wire signed [16:0] diff = $signed({1'b0, val_b}) - $signed({1'b0, val_a});
    wire signed [24:0] scaled = diff * $signed({1'b0, 8'd0, frac});
    wire [15:0] interp = val_a + scaled[23:8];

    integer _i;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            query_val <= 16'd0;
            result_val <= 16'd0;
            for (_i = 0; _i < 64; _i = _i + 1)
                tbl[_i] <= {_i[5:0], 10'd0}; // identity: y ≈ x*1024
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:10] == 2'b00) begin
                    case (reg_addr[4:2])
                        3'h0: begin
                            query_val <= reg_wdata[15:0];
                            result_val <= interp;
                        end
                    endcase
                end else begin
                    // Table write at 0x400+
                    tbl[reg_addr[7:2]] <= reg_wdata[15:0];
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {16'd0, result_val};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
