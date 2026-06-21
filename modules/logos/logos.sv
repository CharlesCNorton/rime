// LOGOS: Logarithmic Operations and General Optimization System
// Log-domain ALU: multiply becomes add, divide becomes subtract.
// Fast shift-based log2 approximation (no lookup tables needed).
// 8.8 fixed-point log representation.
//
// Memory map:
//   0x000: INPUT_A  (write) — 16-bit linear value
//   0x004: INPUT_B  (write) — 16-bit linear value
//   0x008: LOG_A    (read)  — 16-bit log2(A) in 8.8 FP
//   0x00C: LOG_B    (read)  — 16-bit log2(B) in 8.8 FP
//   0x010: MULTIPLY (read)  — antilog(logA + logB) ≈ A * B (16-bit)
//   0x014: DIVIDE   (read)  — antilog(logA - logB) ≈ A / B (16-bit)
//   0x018: SQRT_A   (read)  — antilog(logA >> 1) ≈ sqrt(A) (16-bit)
//   0x01C: CONTROL  (write) — bit 0 = reset

module logos (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    // Priority encoder: find MSB position of a 16-bit value
    function automatic [3:0] find_msb(input [15:0] v);
        begin
            if      (v[15]) find_msb = 4'd15;
            else if (v[14]) find_msb = 4'd14;
            else if (v[13]) find_msb = 4'd13;
            else if (v[12]) find_msb = 4'd12;
            else if (v[11]) find_msb = 4'd11;
            else if (v[10]) find_msb = 4'd10;
            else if (v[ 9]) find_msb = 4'd9;
            else if (v[ 8]) find_msb = 4'd8;
            else if (v[ 7]) find_msb = 4'd7;
            else if (v[ 6]) find_msb = 4'd6;
            else if (v[ 5]) find_msb = 4'd5;
            else if (v[ 4]) find_msb = 4'd4;
            else if (v[ 3]) find_msb = 4'd3;
            else if (v[ 2]) find_msb = 4'd2;
            else if (v[ 1]) find_msb = 4'd1;
            else             find_msb = 4'd0;
        end
    endfunction

    // log2 approximation: integer part = MSB position, fraction = next 8 bits
    // Shift input left so MSB is at bit 15, then take bits [14:7] as fraction.
    function automatic [15:0] fast_log2(input [15:0] v);
        reg [3:0]  msb;
        reg [15:0] shifted;
        begin
            if (v == 16'd0) begin
                fast_log2 = 16'd0;
            end else begin
                msb = find_msb(v);
                // Shift v left by (15 - msb) to normalize MSB to bit 15
                shifted = v << (4'd15 - msb);
                // Integer part = msb, fraction = shifted[14:7]
                fast_log2 = {4'd0, msb, shifted[14:7]};
            end
        end
    endfunction

    // antilog: 2^log_val where log_val is 8.8 fixed-point
    // Integer part selects base power of 2, fraction does linear interpolation
    function automatic [15:0] fast_antilog(input [15:0] log_val);
        reg [3:0]  int_part;
        reg [7:0]  frac;
        reg [15:0] base_val, next_val;
        begin
            int_part = log_val[11:8];
            frac = log_val[7:0];
            if (int_part >= 4'd15)
                fast_antilog = 16'hFFFF;
            else begin
                base_val = 16'd1 << int_part;
                next_val = 16'd1 << (int_part + 4'd1);
                // Linear interpolation: base + (next - base) * frac / 256
                fast_antilog = base_val + (((next_val - base_val) * {8'd0, frac}) >> 8);
            end
        end
    endfunction

    logic [15:0] a_val, b_val;
    wire [15:0] log_a = fast_log2(a_val);
    wire [15:0] log_b = fast_log2(b_val);
    wire [15:0] sum_log  = log_a + log_b;
    wire [15:0] diff_log = (log_a >= log_b) ? (log_a - log_b) : 16'd0;
    wire [15:0] half_log = {1'b0, log_a[15:1]};

    wire [15:0] mul_result  = fast_antilog(sum_log);
    wire [15:0] div_result  = fast_antilog(diff_log);
    wire [15:0] sqrt_result = fast_antilog(half_log);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            a_val <= 16'd0; b_val <= 16'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: a_val <= reg_wdata[15:0];
                    3'h1: b_val <= reg_wdata[15:0];
                    3'h7: begin a_val <= 16'd0; b_val <= 16'd0; end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: reg_rdata <= {16'd0, log_a};
                    3'h3: reg_rdata <= {16'd0, log_b};
                    3'h4: reg_rdata <= {16'd0, mul_result};
                    3'h5: reg_rdata <= {16'd0, div_result};
                    3'h6: reg_rdata <= {16'd0, sqrt_result};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
