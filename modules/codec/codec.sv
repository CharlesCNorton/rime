// CODEC: Compact Ordered Data Encoding/Decoding Coprocessor
// Base64 encode and decode. Feed 3 bytes for encode (produces 4 chars)
// or 4 chars for decode (produces 3 bytes). Single-cycle combinational.
//
// Memory map:
//   0x000: IN0    (write) — input byte/char 0
//   0x004: IN1    (write) — input byte/char 1
//   0x008: IN2    (write) — input byte/char 2
//   0x00C: IN3    (write) — input char 3 (decode only)
//   0x010: ENC0   (read)  — encoded char 0 (ASCII)
//   0x014: ENC1   (read)  — encoded char 1
//   0x018: ENC2   (read)  — encoded char 2
//   0x01C: ENC3   (read)  — encoded char 3
//   0x020: DEC0   (read)  — decoded byte 0
//   0x024: DEC1   (read)  — decoded byte 1
//   0x028: DEC2   (read)  — decoded byte 2
//   0x02C: CONTROL (write) — bit 0 = reset

module codec (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0] in0, in1, in2, in3;

    // Base64 alphabet lookup: 6-bit index -> ASCII char
    function automatic [7:0] b64_enc(input [5:0] idx);
        if (idx < 26) b64_enc = 8'd65 + {2'd0, idx};        // A-Z
        else if (idx < 52) b64_enc = 8'd97 + {2'd0, idx} - 8'd26; // a-z
        else if (idx < 62) b64_enc = 8'd48 + {2'd0, idx} - 8'd52; // 0-9
        else if (idx == 62) b64_enc = 8'd43;                  // +
        else b64_enc = 8'd47;                                  // /
    endfunction

    // Reverse: ASCII char -> 6-bit index (0x3F for invalid)
    function automatic [5:0] b64_dec(input [7:0] ch);
        if (ch >= 8'd65 && ch <= 8'd90)       b64_dec = ch[5:0] - 6'd1;  // A-Z -> 0-25
        else if (ch >= 8'd97 && ch <= 8'd122)  b64_dec = ch[5:0] - 6'd7;        // a-z -> 26-51
        else if (ch >= 8'd48 && ch <= 8'd57)   b64_dec = {2'd0, ch[3:0]} + 6'd52; // 0-9 -> 52-61
        else if (ch == 8'd43)                  b64_dec = 6'd62; // +
        else if (ch == 8'd47)                  b64_dec = 6'd63; // /
        else                                   b64_dec = 6'd0;
    endfunction

    // Encode: 3 bytes -> 4 x 6-bit indices
    wire [23:0] enc_bits = {in0, in1, in2};
    wire [7:0] enc0 = b64_enc(enc_bits[23:18]);
    wire [7:0] enc1 = b64_enc(enc_bits[17:12]);
    wire [7:0] enc2 = b64_enc(enc_bits[11:6]);
    wire [7:0] enc3 = b64_enc(enc_bits[5:0]);

    // Decode: 4 chars -> 3 bytes
    wire [5:0] d0 = b64_dec(in0);
    wire [5:0] d1 = b64_dec(in1);
    wire [5:0] d2 = b64_dec(in2);
    wire [5:0] d3 = b64_dec(in3);
    wire [23:0] dec_bits = {d0, d1, d2, d3};
    wire [7:0] dec0 = dec_bits[23:16];
    wire [7:0] dec1 = dec_bits[15:8];
    wire [7:0] dec2 = dec_bits[7:0];

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            in0 <= 8'd0; in1 <= 8'd0; in2 <= 8'd0; in3 <= 8'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: in0 <= reg_wdata[7:0];
                    4'h1: in1 <= reg_wdata[7:0];
                    4'h2: in2 <= reg_wdata[7:0];
                    4'h3: in3 <= reg_wdata[7:0];
                    4'hB: begin
                        if (reg_wdata[0]) begin
                            in0 <= 8'd0; in1 <= 8'd0; in2 <= 8'd0; in3 <= 8'd0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h4: reg_rdata <= {24'd0, enc0};
                    4'h5: reg_rdata <= {24'd0, enc1};
                    4'h6: reg_rdata <= {24'd0, enc2};
                    4'h7: reg_rdata <= {24'd0, enc3};
                    4'h8: reg_rdata <= {24'd0, dec0};
                    4'h9: reg_rdata <= {24'd0, dec1};
                    4'hA: reg_rdata <= {24'd0, dec2};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
