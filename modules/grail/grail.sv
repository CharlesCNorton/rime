// GRAIL: Merkle tree hasher
// Computes root hash of 8 leaf values using CRC-32 pairwise reduction.
// Level 0: 8 leaves. Level 1: 4 hashes. Level 2: 2 hashes. Level 3: root.
// Each hash combines two 32-bit children by CRC-32(child_a || child_b).
//
// Memory map:
//   0x000-0x01C: LEAF[0..7] (write) — 32-bit leaf values
//   0x020: CONTROL (write) — bit 0 = compute root hash
//   0x024: STATUS  (read)  — bit 0 = done
//   0x028: ROOT    (read)  — 32-bit root hash
//   0x02C: LEVEL1_0 (read) — intermediate hash at level 1, node 0

module grail (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] leaf [0:7];
    logic [31:0] root;
    logic        done;

    // CRC-32 of 8 bytes (two 32-bit words concatenated)
    function automatic [31:0] crc32_pair(input [31:0] a, input [31:0] b);
        logic [31:0] crc;
        logic [63:0] data;
        integer i;
        data = {b, a};
        crc = 32'hFFFFFFFF;
        for (i = 0; i < 64; i = i + 1) begin
            if (crc[0] ^ data[i])
                crc = (crc >> 1) ^ 32'hEDB88320;
            else
                crc = crc >> 1;
        end
        crc32_pair = crc ^ 32'hFFFFFFFF;
    endfunction

    // Multi-cycle Merkle reduction
    logic [31:0] lvl1 [0:3];
    logic [31:0] lvl2 [0:1];
    logic [2:0]  step;
    logic        computing;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            done <= 1'b0; computing <= 1'b0; step <= 3'd0;
            root <= 32'd0;
        end else begin
            if (computing) begin
                case (step)
                    3'd0: begin lvl1[0] <= crc32_pair(leaf[0], leaf[1]); step <= 3'd1; end
                    3'd1: begin lvl1[1] <= crc32_pair(leaf[2], leaf[3]); step <= 3'd2; end
                    3'd2: begin lvl1[2] <= crc32_pair(leaf[4], leaf[5]); step <= 3'd3; end
                    3'd3: begin lvl1[3] <= crc32_pair(leaf[6], leaf[7]); step <= 3'd4; end
                    3'd4: begin lvl2[0] <= crc32_pair(lvl1[0], lvl1[1]); step <= 3'd5; end
                    3'd5: begin lvl2[1] <= crc32_pair(lvl1[2], lvl1[3]); step <= 3'd6; end
                    3'd6: begin root <= crc32_pair(lvl2[0], lvl2[1]); done <= 1'b1; computing <= 1'b0; end
                endcase
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[5] == 1'b0) begin
                    // 0x000-0x01C: leaf writes
                    leaf[reg_addr[4:2]] <= reg_wdata;
                end else begin
                    case (reg_addr[4:2])
                        3'h0: begin // CONTROL
                            if (reg_wdata[0]) begin
                                computing <= 1'b1;
                                done <= 1'b0;
                                step <= 3'd0;
                            end
                        end
                    endcase
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h9: reg_rdata <= {31'd0, done};  // STATUS at 0x024
                    4'hA: reg_rdata <= root;             // ROOT at 0x028
                    4'hB: reg_rdata <= lvl1[0];          // LEVEL1_0 at 0x02C
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
