// FLIP: Fast Logical Interstitial Permutator
// Bit-matrix transposer: 8x8 and 32x32 modes.
// The transpose is pure combinational wiring — zero logic gates.
//
// 8x8 mode: write 8 rows (bits [7:0] of each word), read 8 transposed columns.
// 32x32 mode: write 32 rows (full 32-bit words), read 32 transposed columns.
//
// Memory map:
//   0x000-0x01C: ROW8[0..7]  (write) — 8x8 input rows, bits [7:0]
//   0x020-0x03C: COL8[0..7]  (read)  — 8x8 transposed output
//   0x040:       STATUS      (read)  — bit 0 = 32x32 loaded (all 32 rows written)
//   0x100-0x17C: ROW32[0..31](write) — 32x32 input rows
//   0x200-0x27C: COL32[0..31](read)  — 32x32 transposed output

module flip (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // 8x8 storage
    logic [7:0] row8 [0:7];

    // 32x32 storage
    logic [31:0] row32 [0:31];
    logic [5:0]  loaded_count;

    // 8x8 transpose: col8[j][i] = row8[i][j]
    wire [7:0] col8 [0:7];
    genvar i, j;
    generate
        for (j = 0; j < 8; j = j + 1) begin : gen_col8
            for (i = 0; i < 8; i = i + 1) begin : gen_bit8
                assign col8[j][i] = row8[i][j];
            end
        end
    endgenerate

    // 32x32 transpose: col32[j][i] = row32[i][j]
    wire [31:0] col32 [0:31];
    generate
        for (j = 0; j < 32; j = j + 1) begin : gen_col32
            for (i = 0; i < 32; i = i + 1) begin : gen_bit32
                assign col32[j][i] = row32[i][j];
            end
        end
    endgenerate

    integer _k;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            for (_k = 0; _k < 8; _k = _k + 1)
                row8[_k] <= 8'd0;
            for (_k = 0; _k < 32; _k = _k + 1)
                row32[_k] <= 32'd0;
            loaded_count <= 6'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:8] == 4'h0 && reg_addr[7:5] == 3'b000) begin
                    // 0x000-0x01C: ROW8[0..7]
                    row8[reg_addr[4:2]] <= reg_wdata[7:0];
                end
                if (reg_addr[11:8] == 4'h1) begin
                    // 0x100-0x17C: ROW32[0..31]
                    row32[reg_addr[6:2]] <= reg_wdata;
                    if (loaded_count < 6'd32)
                        loaded_count <= loaded_count + 6'd1;
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:8] == 4'h0) begin
                    if (reg_addr[7:5] == 3'b001) begin
                        // 0x020-0x03C: COL8[0..7]
                        reg_rdata <= {24'd0, col8[reg_addr[4:2]]};
                    end else if (reg_addr[7:2] == 6'h10) begin
                        // 0x040: STATUS
                        reg_rdata <= {31'd0, loaded_count >= 6'd32 ? 1'b1 : 1'b0};
                    end else begin
                        reg_rdata <= 32'd0;
                    end
                end else if (reg_addr[11:8] == 4'h2) begin
                    // 0x200-0x27C: COL32[0..31]
                    reg_rdata <= col32[reg_addr[6:2]];
                end else begin
                    reg_rdata <= 32'd0;
                end
            end
        end
    end
endmodule
