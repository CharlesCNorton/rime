// LACE: Linear Address from Coordinate Encoding
// Z-order bit interleave/deinterleave for 2D and 3D coordinates.
// Pure combinational wiring — zero logic for the interleave itself.
//
// Memory map:
//   0x000: X2D       (write) — 16-bit X for 2D encode
//   0x004: Y2D       (write) — 16-bit Y for 2D encode (triggers latch)
//   0x008: Z2D_OUT   (read)  — 32-bit Morton code from (X2D, Y2D)
//   0x00C: Z2D_IN    (write) — 32-bit Morton code for 2D decode
//   0x010: X2D_OUT   (read)  — 16-bit deinterleaved X
//   0x014: Y2D_OUT   (read)  — 16-bit deinterleaved Y
//   0x018: X3D       (write) — 10-bit X for 3D encode
//   0x01C: Y3D       (write) — 10-bit Y for 3D encode
//   0x020: Z3D       (write) — 10-bit Z for 3D encode (triggers latch)
//   0x024: M3D_OUT   (read)  — 30-bit 3D Morton code
//   0x028: M3D_IN    (write) — 30-bit 3D Morton code for decode
//   0x02C: X3D_OUT   (read)  — 10-bit deinterleaved X
//   0x030: Y3D_OUT   (read)  — 10-bit deinterleaved Y
//   0x034: Z3D_OUT   (read)  — 10-bit deinterleaved Z

module lace (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [15:0] x2d, y2d;
    logic [31:0] z2d_in;
    logic [9:0]  x3d, y3d, z3d;
    logic [29:0] m3d_in;

    // 2D encode: interleave x[i] into even bits, y[i] into odd bits
    wire [31:0] z2d_enc;
    genvar i;
    generate
        for (i = 0; i < 16; i = i + 1) begin : gen_2d_enc
            assign z2d_enc[2*i]     = x2d[i];
            assign z2d_enc[2*i + 1] = y2d[i];
        end
    endgenerate

    // 2D decode: extract even bits to x, odd bits to y
    wire [15:0] x2d_dec, y2d_dec;
    generate
        for (i = 0; i < 16; i = i + 1) begin : gen_2d_dec
            assign x2d_dec[i] = z2d_in[2*i];
            assign y2d_dec[i] = z2d_in[2*i + 1];
        end
    endgenerate

    // 3D encode: interleave x[i], y[i], z[i] into consecutive triples
    wire [29:0] m3d_enc;
    generate
        for (i = 0; i < 10; i = i + 1) begin : gen_3d_enc
            assign m3d_enc[3*i]     = x3d[i];
            assign m3d_enc[3*i + 1] = y3d[i];
            assign m3d_enc[3*i + 2] = z3d[i];
        end
    endgenerate

    // 3D decode: extract every 3rd bit starting at offset 0, 1, 2
    wire [9:0] x3d_dec, y3d_dec, z3d_dec;
    generate
        for (i = 0; i < 10; i = i + 1) begin : gen_3d_dec
            assign x3d_dec[i] = m3d_in[3*i];
            assign y3d_dec[i] = m3d_in[3*i + 1];
            assign z3d_dec[i] = m3d_in[3*i + 2];
        end
    endgenerate

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            x2d    <= 16'd0;
            y2d    <= 16'd0;
            z2d_in <= 32'd0;
            x3d    <= 10'd0;
            y3d    <= 10'd0;
            z3d    <= 10'd0;
            m3d_in <= 30'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: x2d    <= reg_wdata[15:0];
                    4'h1: y2d    <= reg_wdata[15:0];
                    4'h3: z2d_in <= reg_wdata;
                    4'h6: x3d    <= reg_wdata[9:0];
                    4'h7: y3d    <= reg_wdata[9:0];
                    4'h8: z3d    <= reg_wdata[9:0];
                    4'hA: m3d_in <= reg_wdata[29:0];
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h2: reg_rdata <= z2d_enc;
                    4'h4: reg_rdata <= {16'd0, x2d_dec};
                    4'h5: reg_rdata <= {16'd0, y2d_dec};
                    4'h9: reg_rdata <= {2'd0, m3d_enc};
                    4'hB: reg_rdata <= {22'd0, x3d_dec};
                    4'hC: reg_rdata <= {22'd0, y3d_dec};
                    4'hD: reg_rdata <= {22'd0, z3d_dec};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
