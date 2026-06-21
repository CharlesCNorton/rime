// BLOOM: Hardware popcount and bit manipulation
// Single-cycle popcount, leading-zero count, trailing-zero count,
// bit reverse, parity, and Hamming weight.
//
// Memory map:
//   0x000: INPUT   (write) — 32-bit value to analyze
//   0x004: POPCNT  (read)  — number of 1-bits (0-32)
//   0x008: CLZ     (read)  — count of leading zeros (0-32)
//   0x00C: CTZ     (read)  — count of trailing zeros (0-32)
//   0x010: REVERSE (read)  — bit-reversed value
//   0x014: PARITY  (read)  — XOR of all bits (0 or 1)

module bloom (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] val;

    // Popcount
    wire [5:0] popcnt;
    integer _pi;
    assign popcnt = val[0]+val[1]+val[2]+val[3]+val[4]+val[5]+val[6]+val[7]+
                    val[8]+val[9]+val[10]+val[11]+val[12]+val[13]+val[14]+val[15]+
                    val[16]+val[17]+val[18]+val[19]+val[20]+val[21]+val[22]+val[23]+
                    val[24]+val[25]+val[26]+val[27]+val[28]+val[29]+val[30]+val[31];

    // CLZ
    logic [5:0] clz;
    integer _ci;
    always_comb begin
        clz = 6'd32;
        for (_ci = 31; _ci >= 0; _ci = _ci - 1)
            if (val[_ci] && clz == 6'd32)
                clz = 6'd31 - _ci[5:0];
    end

    // CTZ
    logic [5:0] ctz;
    integer _ti;
    always_comb begin
        ctz = 6'd32;
        for (_ti = 0; _ti < 32; _ti = _ti + 1)
            if (val[_ti] && ctz == 6'd32)
                ctz = _ti[5:0];
    end

    // Bit reverse
    wire [31:0] rev;
    genvar gi;
    generate
        for (gi = 0; gi < 32; gi = gi + 1) begin : bitrev
            assign rev[gi] = val[31-gi];
        end
    endgenerate

    // Parity
    wire parity = ^val;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) val <= 32'd0;
        else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[4:2] == 3'h0) val <= reg_wdata;
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {26'd0, popcnt};
                    3'h2: reg_rdata <= {26'd0, clz};
                    3'h3: reg_rdata <= {26'd0, ctz};
                    3'h4: reg_rdata <= rev;
                    3'h5: reg_rdata <= {31'd0, parity};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
