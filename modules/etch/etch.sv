// ETCH: Encrypted Transform with Cyclic Hashing
// XTEA block cipher. 64 Feistel rounds, 32 cycles (2 rounds per cycle).
// 64-bit block (v0, v1), 128-bit key (k[0..3]).
//
// Memory map:
//   0x000: V0      (write/read) — plaintext/ciphertext low word
//   0x004: V1      (write/read) — plaintext/ciphertext high word
//   0x008: KEY0    (write) — key word 0
//   0x00C: KEY1    (write) — key word 1
//   0x010: KEY2    (write) — key word 2
//   0x014: KEY3    (write) — key word 3
//   0x018: CONTROL (write) — bit 0 = encrypt, bit 1 = decrypt, bit 2 = reset
//   0x01C: STATUS  (read)  — bit 0 = done

module etch (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] v0, v1;
    logic [31:0] key [0:3];
    logic        computing;
    logic        done;
    logic        decrypt_mode;
    logic [5:0]  round;
    logic [31:0] sum;

    localparam [31:0] DELTA = 32'h9E3779B9;

    wire [1:0] sum_key_enc = sum[1:0];
    wire [1:0] sum_key_dec = (sum >> 11) & 2'b11;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            v0 <= 32'd0; v1 <= 32'd0;
            key[0] <= 32'd0; key[1] <= 32'd0;
            key[2] <= 32'd0; key[3] <= 32'd0;
            computing <= 1'b0; done <= 1'b0;
            decrypt_mode <= 1'b0;
            round <= 6'd0; sum <= 32'd0;
        end else begin
            if (computing) begin
                // XTEA Feistel round: the core operation is
                //   v += (((v_other << 4) ^ (v_other >> 5)) + v_other) ^ (sum + key[idx])
                // Encrypt advances sum by DELTA and key-selects on sum[1:0].
                // Decrypt reverses: subtracts DELTA and key-selects on (sum>>11)&3.
                if (!decrypt_mode) begin
                    v0 <= v0 + ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (sum + key[sum[1:0]]));
                    sum <= sum + DELTA;
                end else begin
                    v1 <= v1 - ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum >> 11) & 2'b11]));
                    sum <= sum - DELTA;
                end
                if (round == 6'd63) begin
                    computing <= 1'b0;
                    done      <= 1'b1;
                end
                round <= round + 6'd1;
                // Alternate between v0 and v1 updates
                if (!decrypt_mode && round[0]) begin
                    v1 <= v1 + ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (sum + key[(sum >> 11) & 2'b11]));
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: v0 <= reg_wdata;
                    3'h1: v1 <= reg_wdata;
                    3'h2: key[0] <= reg_wdata;
                    3'h3: key[1] <= reg_wdata;
                    3'h4: key[2] <= reg_wdata;
                    3'h5: key[3] <= reg_wdata;
                    3'h6: begin
                        if (reg_wdata[2]) begin
                            v0 <= 32'd0; v1 <= 32'd0;
                            computing <= 1'b0; done <= 1'b0;
                        end
                        if (reg_wdata[0]) begin
                            sum <= 32'd0;
                            round <= 6'd0;
                            decrypt_mode <= 1'b0;
                            computing <= 1'b1;
                            done <= 1'b0;
                        end
                        if (reg_wdata[1]) begin
                            sum <= 32'hC6EF3720;
                            round <= 6'd0;
                            decrypt_mode <= 1'b1;
                            computing <= 1'b1;
                            done <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= v0;
                    3'h1: reg_rdata <= v1;
                    3'h7: reg_rdata <= {31'd0, done};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
