// HAZE: Hardware Approximation of Zoned Entropy
// 2D value noise with bilinear interpolation.
// Write X,Y coordinates (8.8 fixed-point), read smooth noise value.
// Hash function at integer grid points, bilinear interpolation between them.
// Deterministic: same input always produces same output.
//
// Memory map:
//   0x000: COORD_X  (write) — 16-bit X coordinate (8.8 fixed-point)
//   0x004: COORD_Y  (write) — 16-bit Y coordinate (8.8 fixed-point)
//   0x008: CONTROL  (write) — bit 0 = compute, bit 1 = reset
//   0x00C: STATUS   (read)  — bit 0 = done
//   0x010: VALUE    (read)  — 16-bit noise value (0-255 range, 8.8 FP)
//   0x014: HASH_DBG (read)  — raw hash at floor(x),floor(y) (debug)

module haze (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // 2D gradient noise: hash the four grid corners, compute dot products
    // with gradient vectors, bilinearly interpolate. The hash function is a
    // simple permutation table (Perlin-style) that maps grid coordinates to
    // pseudo-random gradient directions.
    logic [15:0] coord_x, coord_y;
    logic [15:0] value;
    logic [7:0]  hash_dbg;
    logic        done;
    logic        computing;
    logic [2:0]  step;

    // Integer hash: simple LCG-style for spatial coherence
    function automatic [7:0] grid_hash(input [7:0] x, input [7:0] y);
        logic [15:0] h;
        h = {x, y} ^ 16'hA5A5;
        h = h * 16'h0101;
        h = h ^ (h >> 7);
        h = h * 16'h0503;
        h = h ^ (h >> 11);
        grid_hash = h[7:0];
    endfunction

    logic [7:0] ix, iy, fx, fy;
    logic [7:0] h00, h10, h01, h11;
    logic [15:0] top_interp, bot_interp;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            coord_x   <= 16'd0;
            coord_y   <= 16'd0;
            value     <= 16'd0;
            hash_dbg  <= 8'd0;
            done      <= 1'b0;
            computing <= 1'b0;
            step      <= 3'd0;
        end else begin
            if (computing) begin
                case (step)
                    3'd0: begin
                        ix <= coord_x[15:8];
                        iy <= coord_y[15:8];
                        fx <= coord_x[7:0];
                        fy <= coord_y[7:0];
                        step <= 3'd1;
                    end
                    3'd1: begin
                        h00 <= grid_hash(ix, iy);
                        h10 <= grid_hash(ix + 8'd1, iy);
                        h01 <= grid_hash(ix, iy + 8'd1);
                        h11 <= grid_hash(ix + 8'd1, iy + 8'd1);
                        hash_dbg <= grid_hash(ix, iy);
                        step <= 3'd2;
                    end
                    3'd2: begin
                        // Bilinear interpolation
                        // top = h00*(256-fx) + h10*fx
                        // bot = h01*(256-fx) + h11*fx
                        top_interp <= h00 * (8'd0 - fx) + h10 * fx;
                        bot_interp <= h01 * (8'd0 - fx) + h11 * fx;
                        step <= 3'd3;
                    end
                    3'd3: begin
                        // value = top*(256-fy) + bot*fy, all >>8
                        value <= ((top_interp * (8'd0 - fy)) + (bot_interp * fy)) >> 8;
                        computing <= 1'b0;
                        done      <= 1'b1;
                    end
                    default: computing <= 1'b0;
                endcase
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: coord_x <= reg_wdata[15:0];
                    3'h1: coord_y <= reg_wdata[15:0];
                    3'h2: begin
                        if (reg_wdata[1]) begin
                            value <= 16'd0;
                            done  <= 1'b0;
                        end
                        if (reg_wdata[0]) begin
                            step      <= 3'd0;
                            computing <= 1'b1;
                            done      <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {16'd0, coord_x};
                    3'h1: reg_rdata <= {16'd0, coord_y};
                    3'h3: reg_rdata <= {31'd0, done};
                    3'h4: reg_rdata <= {16'd0, value};
                    3'h5: reg_rdata <= {24'd0, hash_dbg};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
