// VIGIL: Hamming(7,4) SEC (Single Error Correction) codec
//
// Standard Hamming(7,4) with bit positions 1-7:
//   Position: 1    2    3    4    5    6    7
//   Content:  p1   p2   d1   p3   d2   d3   d4
//   Index:    [0]  [1]  [2]  [3]  [4]  [5]  [6]
//
// Memory map:
//   0x000: ENCODE   (write) — 4-bit data [3:0] → 7-bit codeword
//   0x004: CODED    (read)  — last encoded codeword
//   0x008: DECODE   (write) — 7-bit codeword [6:0] → decode+correct
//   0x00C: DATA     (read)  — decoded 4 data bits
//   0x010: SYNDROME (read)  — syndrome (0=no error, 1-7=error position)
//   0x014: CORRECTED (read) — 1 if correction applied
//   0x018: CONTROL  (write) — bit 0 = reset error counter
//   0x01C: ERRORS   (read)  — total corrected errors

module vigil (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    logic [6:0] coded;
    logic [3:0] decoded_data;
    logic [2:0] last_syndrome;
    logic       last_corrected;
    logic [31:0] error_count;

    // Encode: data[3:0] = {d4, d3, d2, d1}
    wire [3:0] enc_d = reg_wdata[3:0];
    wire enc_p1 = enc_d[0] ^ enc_d[1] ^ enc_d[3]; // d1^d2^d4
    wire enc_p2 = enc_d[0] ^ enc_d[2] ^ enc_d[3]; // d1^d3^d4
    wire enc_p3 = enc_d[1] ^ enc_d[2] ^ enc_d[3]; // d2^d3^d4
    wire [6:0] encoded = {enc_d[3], enc_d[2], enc_d[1], enc_p3, enc_d[0], enc_p2, enc_p1};

    // Decode
    wire [6:0] dec_in = reg_wdata[6:0];
    wire ds1 = dec_in[0] ^ dec_in[2] ^ dec_in[4] ^ dec_in[6]; // positions 1,3,5,7
    wire ds2 = dec_in[1] ^ dec_in[2] ^ dec_in[5] ^ dec_in[6]; // positions 2,3,6,7
    wire ds3 = dec_in[3] ^ dec_in[4] ^ dec_in[5] ^ dec_in[6]; // positions 4,5,6,7
    wire [2:0] syn = {ds3, ds2, ds1};
    // Correct: flip bit at position syn-1 (0-indexed)
    wire [6:0] fixed = (syn != 3'd0) ? (dec_in ^ (7'd1 << (syn - 3'd1))) : dec_in;
    // Extract data: d1=[2], d2=[4], d3=[5], d4=[6]
    wire [3:0] dec_data = {fixed[6], fixed[5], fixed[4], fixed[2]};

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            coded <= 7'd0; decoded_data <= 4'd0;
            last_syndrome <= 3'd0; last_corrected <= 1'b0;
            error_count <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: coded <= encoded;
                    3'h2: begin
                        decoded_data <= dec_data;
                        last_syndrome <= syn;
                        last_corrected <= (syn != 3'd0);
                        if (syn != 3'd0) error_count <= error_count + 32'd1;
                    end
                    3'h6: if (reg_wdata[0]) error_count <= 32'd0;
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {25'd0, coded};
                    3'h3: reg_rdata <= {28'd0, decoded_data};
                    3'h4: reg_rdata <= {29'd0, last_syndrome};
                    3'h5: reg_rdata <= {31'd0, last_corrected};
                    3'h7: reg_rdata <= error_count;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
