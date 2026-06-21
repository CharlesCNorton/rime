// PRISM: Color space converter
// RGB888 to grayscale luminance using ITU-R BT.601:
//   Y = 0.299*R + 0.587*G + 0.114*B
// Fixed-point: Y = (77*R + 150*G + 29*B) >> 8
// Also provides min/max channel and saturation estimate.
//
// Memory map:
//   0x000: RGB     (write) — bits [23:16]=R, [15:8]=G, [7:0]=B
//   0x004: LUMA    (read)  — 8-bit luminance Y
//   0x008: MIN_CH  (read)  — minimum of R,G,B
//   0x00C: MAX_CH  (read)  — maximum of R,G,B
//   0x010: SAT     (read)  — max-min (saturation estimate)
//   0x014: INVERT  (read)  — inverted RGB (255-R, 255-G, 255-B)

module prism (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0] r, g, b;

    // Luminance: (77*R + 150*G + 29*B) >> 8
    wire [15:0] luma_full = 16'd77 * r + 16'd150 * g + 16'd29 * b;
    wire [7:0]  luma = luma_full[15:8];

    // Min/Max
    wire [7:0] min_rg = (r < g) ? r : g;
    wire [7:0] min_ch = (min_rg < b) ? min_rg : b;
    wire [7:0] max_rg = (r > g) ? r : g;
    wire [7:0] max_ch = (max_rg > b) ? max_rg : b;
    wire [7:0] sat = max_ch - min_ch;

    // Hue: 0-252 (6 sectors of 42 each, approximating 0-360)
    // Sector 0: R=max, G rising → hue = 42*(G-B)/(max-min)
    // Simplified: hue sector from max channel, delta approximation
    logic [7:0] hue;
    always_comb begin
        if (sat == 8'd0)
            hue = 8'd0;
        else if (max_ch == r && g >= b)
            hue = 42 * (g - b) / sat;
        else if (max_ch == r)
            hue = 252 - 42 * (b - g) / sat;
        else if (max_ch == g)
            hue = 84 + 42 * (b - r) / sat;
        else
            hue = 168 + 42 * (r - g) / sat;
    end

    // V = max channel
    wire [7:0] val = max_ch;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            r <= 8'd0; g <= 8'd0; b <= 8'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[4:2] == 3'h0) begin
                    r <= reg_wdata[23:16];
                    g <= reg_wdata[15:8];
                    b <= reg_wdata[7:0];
                end
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {24'd0, luma};
                    3'h2: reg_rdata <= {24'd0, min_ch};
                    3'h3: reg_rdata <= {24'd0, max_ch};
                    3'h4: reg_rdata <= {24'd0, sat};
                    3'h5: reg_rdata <= {8'd0, 8'd255 - r, 8'd255 - g, 8'd255 - b};
                    3'h6: reg_rdata <= {24'd0, hue};   // HSV hue (0-252)
                    3'h7: reg_rdata <= {24'd0, val};   // HSV value (=max)
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
