// PHASE: Periodic Hardware Accumulation and Signal Encoder
// Quadrature decoder. Software-driven A/B inputs, 32-bit position counter,
// direction flag, edge counter. For testing, A and B are written via registers.
//
// Memory map:
//   0x000: AB_INPUT  (write) — bit 0 = A, bit 1 = B (software-driven for testing)
//   0x004: POSITION  (read)  — signed 32-bit position counter
//   0x008: DIRECTION (read)  — 0 = stopped, 1 = forward, 2 = reverse
//   0x00C: EDGES     (read)  — total edge count (unsigned)
//   0x010: CONTROL   (write) — bit 0 = reset, bit 1 = sample (latch AB and update)
//   0x014: STATUS    (read)  — bits [1:0] = last A,B values

module phase (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic       a_cur, b_cur;
    logic       a_prev, b_prev;
    logic [31:0] position;
    logic [1:0]  direction;
    logic [31:0] edges;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            a_cur    <= 1'b0;
            b_cur    <= 1'b0;
            a_prev   <= 1'b0;
            b_prev   <= 1'b0;
            position <= 32'd0;
            direction <= 2'd0;
            edges    <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        a_cur <= reg_wdata[0];
                        b_cur <= reg_wdata[1];
                    end
                    3'h4: begin
                        if (reg_wdata[0]) begin
                            position  <= 32'd0;
                            direction <= 2'd0;
                            edges     <= 32'd0;
                            a_prev    <= 1'b0;
                            b_prev    <= 1'b0;
                        end
                        if (reg_wdata[1]) begin
                            // Decode quadrature: standard gray-code state machine
                            logic [1:0] prev_state, cur_state;
                            logic signed [1:0] delta;
                            prev_state = {b_prev, a_prev};
                            cur_state  = {b_cur, a_cur};
                            delta = 2'sd0;
                            case ({prev_state, cur_state})
                                4'b00_01: delta = 2'sd1;
                                4'b01_11: delta = 2'sd1;
                                4'b11_10: delta = 2'sd1;
                                4'b10_00: delta = 2'sd1;
                                4'b01_00: delta = -2'sd1;
                                4'b11_01: delta = -2'sd1;
                                4'b10_11: delta = -2'sd1;
                                4'b00_10: delta = -2'sd1;
                                default:  delta = 2'sd0;
                            endcase
                            if (delta != 2'sd0) begin
                                position <= position + {{30{delta[1]}}, delta};
                                edges    <= edges + 32'd1;
                                direction <= (delta[1]) ? 2'd2 : 2'd1;
                            end else begin
                                direction <= 2'd0;
                            end
                            a_prev <= a_cur;
                            b_prev <= b_cur;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {30'd0, b_cur, a_cur};
                    3'h1: reg_rdata <= position;
                    3'h2: reg_rdata <= {30'd0, direction};
                    3'h3: reg_rdata <= edges;
                    3'h5: reg_rdata <= {30'd0, b_prev, a_prev};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
