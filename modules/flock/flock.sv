// FLOCK: 4-agent boids simulation with Reynolds flocking
// Each agent has position (x,y) and velocity (vx,vy) in 8-bit signed.
// Step applies three forces:
//   1. Cohesion:    steer toward group centroid
//   2. Separation:  repel from agents within distance threshold
//   3. Alignment:   steer toward average group velocity
// Velocity clamped to [-16, 16].
//
// Memory map:
//   0x000: STEP    (write) — bit 0 = step one tick
//   0x004: STATUS  (read)  — bits [7:0] = step count
//   0x008: RESET   (write) — bit 0 = reset to initial positions
//   0x010: X0      (read)  — agent 0 X position (signed 8-bit)
//   0x014: Y0      (read)
//   0x018: X1      (read)
//   0x01C: Y1      (read)
//   0x020: X2      (read)
//   0x024: Y2      (read)
//   0x028: X3      (read)
//   0x02C: Y3      (read)

module flock (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic signed [7:0] x [0:3];
    logic signed [7:0] y [0:3];
    logic signed [7:0] vx [0:3];
    logic signed [7:0] vy [0:3];
    logic [7:0] steps;

    localparam signed [7:0] SEP_DIST = 8'sd8;

    wire signed [9:0] cx = ({{2{x[0][7]}},x[0]}+{{2{x[1][7]}},x[1]}+{{2{x[2][7]}},x[2]}+{{2{x[3][7]}},x[3]}) >>> 2;
    wire signed [9:0] cy = ({{2{y[0][7]}},y[0]}+{{2{y[1][7]}},y[1]}+{{2{y[2][7]}},y[2]}+{{2{y[3][7]}},y[3]}) >>> 2;

    wire signed [9:0] avg_vx = ({{2{vx[0][7]}},vx[0]}+{{2{vx[1][7]}},vx[1]}+{{2{vx[2][7]}},vx[2]}+{{2{vx[3][7]}},vx[3]}) >>> 2;
    wire signed [9:0] avg_vy = ({{2{vy[0][7]}},vy[0]}+{{2{vy[1][7]}},vy[1]}+{{2{vy[2][7]}},vy[2]}+{{2{vy[3][7]}},vy[3]}) >>> 2;

    function automatic signed [7:0] clamp(input signed [9:0] v);
        if (v > 10'sd16) clamp = 8'sd16;
        else if (v < -10'sd16) clamp = -8'sd16;
        else clamp = v[7:0];
    endfunction

    function automatic signed [7:0] abs8(input signed [7:0] v);
        abs8 = v[7] ? -v : v;
    endfunction

    integer _i, _j;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            x[0]<=8'sd10;  y[0]<=8'sd10;  vx[0]<=8'sd1;  vy[0]<=8'sd0;
            x[1]<=-8'sd10; y[1]<=8'sd10;  vx[1]<=8'sd0;  vy[1]<=8'sd1;
            x[2]<=8'sd10;  y[2]<=-8'sd10; vx[2]<=-8'sd1; vy[2]<=8'sd0;
            x[3]<=-8'sd10; y[3]<=-8'sd10; vx[3]<=8'sd0;  vy[3]<=-8'sd1;
            steps <= 8'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: if (reg_wdata[0]) begin
                        // All four agents update simultaneously in one clock cycle.
                        // Arithmetic uses 10-bit signed to prevent overflow during
                        // accumulation, then clamps back to [-16, 16] for storage.
                        // The >>> 3 shifts scale forces down by 1/8 for stability.
                        for (_i = 0; _i < 4; _i = _i + 1) begin
                            logic signed [9:0] nvx, nvy;
                            logic signed [9:0] sep_x, sep_y;

                            // Cohesion: steer toward centroid
                            nvx = {{2{vx[_i][7]}}, vx[_i]} + ((cx - {{2{x[_i][7]}}, x[_i]}) >>> 3);
                            nvy = {{2{vy[_i][7]}}, vy[_i]} + ((cy - {{2{y[_i][7]}}, y[_i]}) >>> 3);

                            // Separation: repel from nearby agents
                            sep_x = 10'sd0;
                            sep_y = 10'sd0;
                            for (_j = 0; _j < 4; _j = _j + 1) begin
                                if (_j != _i) begin
                                    if (abs8(x[_i] - x[_j]) < SEP_DIST && abs8(y[_i] - y[_j]) < SEP_DIST) begin
                                        sep_x = sep_x + ({{2{x[_i][7]}}, x[_i]} - {{2{x[_j][7]}}, x[_j]});
                                        sep_y = sep_y + ({{2{y[_i][7]}}, y[_i]} - {{2{y[_j][7]}}, y[_j]});
                                    end
                                end
                            end
                            nvx = nvx + (sep_x >>> 2);
                            nvy = nvy + (sep_y >>> 2);

                            // Alignment: steer toward average velocity
                            nvx = nvx + ((avg_vx - {{2{vx[_i][7]}}, vx[_i]}) >>> 3);
                            nvy = nvy + ((avg_vy - {{2{vy[_i][7]}}, vy[_i]}) >>> 3);

                            vx[_i] <= clamp(nvx);
                            vy[_i] <= clamp(nvy);
                            x[_i] <= x[_i] + clamp(nvx);
                            y[_i] <= y[_i] + clamp(nvy);
                        end
                        steps <= steps + 8'd1;
                    end
                    4'h2: if (reg_wdata[0]) begin
                        x[0]<=8'sd10;  y[0]<=8'sd10;
                        x[1]<=-8'sd10; y[1]<=8'sd10;
                        x[2]<=8'sd10;  y[2]<=-8'sd10;
                        x[3]<=-8'sd10; y[3]<=-8'sd10;
                        vx[0]<=8'sd1; vy[0]<=8'sd0;
                        vx[1]<=8'sd0; vy[1]<=8'sd1;
                        vx[2]<=-8'sd1; vy[2]<=8'sd0;
                        vx[3]<=8'sd0; vy[3]<=-8'sd1;
                        steps <= 8'd0;
                    end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h1: reg_rdata <= {24'd0, steps};
                    4'h4: reg_rdata <= {{24{x[0][7]}}, x[0]};
                    4'h5: reg_rdata <= {{24{y[0][7]}}, y[0]};
                    4'h6: reg_rdata <= {{24{x[1][7]}}, x[1]};
                    4'h7: reg_rdata <= {{24{y[1][7]}}, y[1]};
                    4'h8: reg_rdata <= {{24{x[2][7]}}, x[2]};
                    4'h9: reg_rdata <= {{24{y[2][7]}}, y[2]};
                    4'hA: reg_rdata <= {{24{x[3][7]}}, x[3]};
                    4'hB: reg_rdata <= {{24{y[3][7]}}, y[3]};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
