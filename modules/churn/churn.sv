// CHURN: Continuous Hash Updating and Rolling Node
// 32-byte window Rabin-Karp rolling hash.
// hash = sum(window[i] * BASE^(W-1-i)) mod 2^32 (implicit mod via overflow).
// On each byte: hash = hash * BASE - old * BASE^W + new.
// BASE = 31, BASE^32 precomputed.
//
// Memory map:
//   0x000: DATA      (write) — feed one byte, hash updates
//   0x004: HASH      (read)  — current 32-bit rolling hash
//   0x008: CONTROL   (write) — bit 0 = reset
//   0x00C: BOUNDARY  (read)  — bit 0 = (hash & mask) == 0
//   0x010: TARGET    (write) — 32-bit boundary mask
//   0x014: BYTECOUNT (read)  — bytes fed since last reset

module churn (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    localparam W = 32;
    localparam [31:0] BASE = 32'd31;
    // BASE^32 mod 2^32 (precomputed: 31^32 mod 2^32)
    localparam [31:0] BASE_POW_W = 32'hD18B4A81;

    logic [7:0]  window [0:W-1];
    logic [4:0]  wptr;
    logic [31:0] hash;
    logic [31:0] mask;
    logic [31:0] byte_count;
    logic        filled;  // window has >= W bytes

    integer _i;
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            hash <= 32'd0; mask <= 32'h0000000F;
            wptr <= 5'd0; filled <= 1'b0; byte_count <= 32'd0;
            for (_i = 0; _i < W; _i = _i + 1) window[_i] <= 8'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        // Feed byte
                        if (filled) begin
                            hash <= (hash * BASE) - ({24'd0, window[wptr]} * BASE_POW_W) + {24'd0, reg_wdata[7:0]};
                        end else begin
                            hash <= (hash * BASE) + {24'd0, reg_wdata[7:0]};
                        end
                        window[wptr] <= reg_wdata[7:0];
                        if (wptr == W - 1) begin
                            wptr <= 5'd0;
                            filled <= 1'b1;
                        end else begin
                            wptr <= wptr + 5'd1;
                        end
                        byte_count <= byte_count + 32'd1;
                    end
                    3'h2: begin
                        hash <= 32'd0; wptr <= 5'd0; filled <= 1'b0; byte_count <= 32'd0;
                        for (_i = 0; _i < W; _i = _i + 1) window[_i] <= 8'd0;
                    end
                    3'h4: mask <= reg_wdata;
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= hash;
                    3'h3: reg_rdata <= {31'd0, (hash & mask) == 32'd0 ? 1'b1 : 1'b0};
                    3'h5: reg_rdata <= byte_count;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
