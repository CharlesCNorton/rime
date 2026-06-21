// MORTAR: 2x2 signed 8-bit matrix multiply
// C = A * B where A, B, C are 2x2 matrices of signed 8-bit elements.
// Result elements are 16-bit (to hold the full product sum).
// Single-cycle combinational multiply.
//
// Memory map:
//   0x000: A00 (write) — signed 8-bit
//   0x004: A01 (write)
//   0x008: A10 (write)
//   0x00C: A11 (write)
//   0x010: B00 (write)
//   0x014: B01 (write)
//   0x018: B10 (write)
//   0x01C: B11 (write)
//   0x020: C00 (read) — signed 16-bit result
//   0x024: C01 (read)
//   0x028: C10 (read)
//   0x02C: C11 (read)

module mortar (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic signed [7:0] a00, a01, a10, a11;
    logic signed [7:0] b00, b01, b10, b11;

    // C = A * B (2x2)
    wire signed [15:0] c00 = a00 * b00 + a01 * b10;
    wire signed [15:0] c01 = a00 * b01 + a01 * b11;
    wire signed [15:0] c10 = a10 * b00 + a11 * b10;
    wire signed [15:0] c11 = a10 * b01 + a11 * b11;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            a00<=0; a01<=0; a10<=0; a11<=0;
            b00<=0; b01<=0; b10<=0; b11<=0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: a00 <= reg_wdata[7:0];
                    3'h1: a01 <= reg_wdata[7:0];
                    3'h2: a10 <= reg_wdata[7:0];
                    3'h3: a11 <= reg_wdata[7:0];
                    3'h4: b00 <= reg_wdata[7:0];
                    3'h5: b01 <= reg_wdata[7:0];
                    3'h6: b10 <= reg_wdata[7:0];
                    3'h7: b11 <= reg_wdata[7:0];
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h8: reg_rdata <= {{16{c00[15]}}, c00};
                    4'h9: reg_rdata <= {{16{c01[15]}}, c01};
                    4'hA: reg_rdata <= {{16{c10[15]}}, c10};
                    4'hB: reg_rdata <= {{16{c11[15]}}, c11};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
