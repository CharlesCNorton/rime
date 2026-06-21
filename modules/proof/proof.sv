// PROOF: Protected Read-Once Operational Fence
// Constant-time 32-byte comparison. Load two 32-byte buffers (A and B),
// trigger compare, read result. The comparison XORs all byte pairs and
// OR-reduces the result — timing is independent of where the mismatch is.
//
// Memory map:
//   0x000-0x01C: BUF_A[0..7] (write) — 32 bytes as 8 x 32-bit words
//   0x020-0x03C: BUF_B[0..7] (write) — 32 bytes as 8 x 32-bit words
//   0x040:       CONTROL      (write) — bit 0 = compare, bit 1 = reset
//   0x044:       RESULT       (read)  — 1 = match, 0 = mismatch
//   0x048:       STATUS       (read)  — bit 0 = done
//   0x04C:       DIFF_OR      (read)  — OR of all XOR diffs (0 = match)

module proof (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] buf_a [0:7];
    logic [31:0] buf_b [0:7];
    logic        done;
    logic [31:0] diff_or;

    wire [31:0] xor0 = buf_a[0] ^ buf_b[0];
    wire [31:0] xor1 = buf_a[1] ^ buf_b[1];
    wire [31:0] xor2 = buf_a[2] ^ buf_b[2];
    wire [31:0] xor3 = buf_a[3] ^ buf_b[3];
    wire [31:0] xor4 = buf_a[4] ^ buf_b[4];
    wire [31:0] xor5 = buf_a[5] ^ buf_b[5];
    wire [31:0] xor6 = buf_a[6] ^ buf_b[6];
    wire [31:0] xor7 = buf_a[7] ^ buf_b[7];
    wire [31:0] all_xor = xor0 | xor1 | xor2 | xor3 | xor4 | xor5 | xor6 | xor7;
    wire         match = (all_xor == 32'd0);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            done    <= 1'b0;
            diff_or <= 32'd0;
            for (integer i = 0; i < 8; i = i + 1) begin
                buf_a[i] <= 32'd0;
                buf_b[i] <= 32'd0;
            end
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b0)
                    buf_a[reg_addr[4:2]] <= reg_wdata;
                else if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b1)
                    buf_b[reg_addr[4:2]] <= reg_wdata;
                else if (reg_addr[6:2] == 5'h10) begin
                    if (reg_wdata[1]) begin
                        done <= 1'b0;
                        diff_or <= 32'd0;
                        for (integer i = 0; i < 8; i = i + 1) begin
                            buf_a[i] <= 32'd0;
                            buf_b[i] <= 32'd0;
                        end
                    end
                    if (reg_wdata[0]) begin
                        diff_or <= all_xor;
                        done    <= 1'b1;
                    end
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[6:2])
                    5'h11: reg_rdata <= {31'd0, done & match};
                    5'h12: reg_rdata <= {31'd0, done};
                    5'h13: reg_rdata <= diff_or;
                    default: begin
                        if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b0)
                            reg_rdata <= buf_a[reg_addr[4:2]];
                        else if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b1)
                            reg_rdata <= buf_b[reg_addr[4:2]];
                        else
                            reg_rdata <= 32'd0;
                    end
                endcase
            end
        end
    end
endmodule
