// ORBIT: Optimized Rotation and Basic Iteration Toolkit
// 20-iteration CORDIC: sin, cos, atan2, magnitude.
// Rotation mode: input angle -> (cos, sin).
// Vectoring mode: input (x, y) -> (magnitude, phase).
// Fixed-point 1.15.16 format. 20 cycles per computation.
//
// Memory map:
//   0x000: ANGLE   (write) — input angle (rotation mode), 1.15.16 fixed-point radians
//   0x004: INPUT_X (write) — X input (vectoring mode)
//   0x008: INPUT_Y (write) — Y input (vectoring mode)
//   0x00C: CONTROL (write) — bit 0 = start, bit 1 = mode (0=rotation, 1=vectoring)
//   0x010: STATUS  (read)  — bit 0 = done
//   0x014: COS_MAG (read)  — X result (cos in rotation, magnitude in vectoring)
//   0x018: SIN_PHS (read)  — Y result (sin in rotation, phase in vectoring)
//   0x01C: RESIDUAL(read)  — Z residual

module orbit (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    localparam N = 20;  // iterations

    // atan(2^-i) in 1.15.16 fixed-point
    logic [31:0] atan_table [0:N-1];
    initial begin
        atan_table[ 0] = 32'h0000C910; // atan(1)     = 0.7854
        atan_table[ 1] = 32'h000076B2; // atan(0.5)   = 0.4636
        atan_table[ 2] = 32'h00003EB7; // atan(0.25)  = 0.2450
        atan_table[ 3] = 32'h00001FD6; // atan(0.125) = 0.1244
        atan_table[ 4] = 32'h00000FFB; // 0.0624
        atan_table[ 5] = 32'h000007FF; // 0.0312
        atan_table[ 6] = 32'h00000400; // 0.0156
        atan_table[ 7] = 32'h00000200; // 0.0078
        atan_table[ 8] = 32'h00000100; // 0.0039
        atan_table[ 9] = 32'h00000080; // 0.00195
        atan_table[10] = 32'h00000040;
        atan_table[11] = 32'h00000020;
        atan_table[12] = 32'h00000010;
        atan_table[13] = 32'h00000008;
        atan_table[14] = 32'h00000004;
        atan_table[15] = 32'h00000002;
        atan_table[16] = 32'h00000001;
        atan_table[17] = 32'h00000001;
        atan_table[18] = 32'h00000000;
        atan_table[19] = 32'h00000000;
    end

    // K = product(cos(atan(2^-i))) for i=0..19 in 1.15.16 = ~0.60725 * 65536
    localparam signed [31:0] K_INIT = 32'sh00009B75; // 0.60725 in 1.15.16

    logic signed [31:0] x, y, z;
    logic signed [31:0] angle_in, x_in, y_in;
    logic [4:0]  iter;
    logic        computing;
    logic        done;
    logic        vec_mode;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            computing <= 1'b0; done <= 1'b0;
            x <= 0; y <= 0; z <= 0; iter <= 0;
            angle_in <= 0; x_in <= 0; y_in <= 0; vec_mode <= 1'b0;
        end else begin
            if (computing) begin
                if (iter < N) begin
                    logic signed [31:0] x_shift, y_shift;
                    x_shift = x >>> iter;
                    y_shift = y >>> iter;
                    if (!vec_mode) begin
                        // Rotation: drive z to zero
                        if (z >= 0) begin
                            x <= x - y_shift;
                            y <= y + x_shift;
                            z <= z - $signed(atan_table[iter]);
                        end else begin
                            x <= x + y_shift;
                            y <= y - x_shift;
                            z <= z + $signed(atan_table[iter]);
                        end
                    end else begin
                        // Vectoring: drive y to zero
                        if (y < 0) begin
                            x <= x - y_shift;
                            y <= y + x_shift;
                            z <= z - $signed(atan_table[iter]);
                        end else begin
                            x <= x + y_shift;
                            y <= y - x_shift;
                            z <= z + $signed(atan_table[iter]);
                        end
                    end
                    iter <= iter + 5'd1;
                end else begin
                    computing <= 1'b0;
                    done <= 1'b1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: angle_in <= $signed(reg_wdata);
                    3'h1: x_in <= $signed(reg_wdata);
                    3'h2: y_in <= $signed(reg_wdata);
                    3'h3: begin
                        vec_mode <= reg_wdata[1];
                        if (reg_wdata[0]) begin
                            if (reg_wdata[1]) begin
                                // Vectoring mode: x=x_in, y=y_in, z=0
                                x <= x_in;
                                y <= y_in;
                                z <= 32'sh0;
                            end else begin
                                // Rotation mode: x=K, y=0, z=angle
                                x <= K_INIT;
                                y <= 32'sh0;
                                z <= angle_in;
                            end
                            iter <= 5'd0;
                            computing <= 1'b1;
                            done <= 1'b0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h4: reg_rdata <= {31'd0, done};
                    3'h5: reg_rdata <= x;
                    3'h6: reg_rdata <= y;
                    3'h7: reg_rdata <= z;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
