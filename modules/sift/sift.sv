// SIFT: Set Intersection Filter Tile
// Hardware Bloom filter with 3 independent hash functions.
// 2048-bit filter array in distributed RAM. Single-cycle insert and query.
//
// Memory map (region 0x3xxxxxxx):
//   0x000: INSERT (write) — hash and set bits for the written value
//   0x004: QUERY  (write value, read result) — write key, then read:
//          result bit 0 = 1 if probably in set, 0 if definitely not
//   0x008: CONTROL (write) — bit 0 = clear all
//   0x00C: COUNT  (read) — number of insertions since last clear
//   0x010: POPCOUNT (read) — number of set bits in filter

module sift (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // 256-bit filter array stored as individual bits (synthesizes to LUT FFs)
    logic [255:0] filter;

    logic [15:0] insert_count;

    // Three hash functions producing 8-bit indices (0-255)
    function automatic [7:0] hash1(input [31:0] key);
        logic [31:0] h;
        h = key ^ (key >> 16);
        h = h * 32'h45d9f3b;
        hash1 = h[7:0];
    endfunction

    function automatic [7:0] hash2(input [31:0] key);
        logic [31:0] h;
        h = key ^ (key >> 13);
        h = h * 32'h2e1b27a5;
        hash2 = h[15:8];
    endfunction

    function automatic [7:0] hash3(input [31:0] key);
        logic [31:0] h;
        h = key ^ (key >> 7);
        h = h * 32'h1a85ec53;
        hash3 = h[23:16];
    endfunction

    wire [7:0] h1 = hash1(reg_wdata);
    wire [7:0] h2 = hash2(reg_wdata);
    wire [7:0] h3 = hash3(reg_wdata);

    // Query result: all 3 bits must be set
    wire query_result = filter[h1] & filter[h2] & filter[h3];

    // Popcount
    logic [8:0] popcount;
    integer _pc_i;
    always_comb begin
        popcount = 9'd0;
        for (_pc_i = 0; _pc_i < 256; _pc_i = _pc_i + 1)
            popcount = popcount + {8'd0, filter[_pc_i]};
    end

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            insert_count <= 16'd0;
            filter <= 256'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin // 0x000: INSERT
                        filter[h1] <= 1'b1;
                        filter[h2] <= 1'b1;
                        filter[h3] <= 1'b1;
                        insert_count <= insert_count + 16'd1;
                    end
                    3'h1: begin // 0x004: QUERY (write key, result on read)
                    end
                    3'h2: begin // 0x008: CONTROL
                        if (reg_wdata[0]) begin
                            filter <= 256'd0;
                            insert_count <= 16'd0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {16'd0, insert_count};  // 0x000: COUNT
                    3'h1: reg_rdata <= {31'd0, query_result};  // 0x004: QUERY result
                    3'h2: reg_rdata <= 32'd0;                  // 0x008: CONTROL (write-only)
                    3'h3: reg_rdata <= {16'd0, insert_count};  // 0x00C: COUNT (alias)
                    3'h4: reg_rdata <= {23'd0, popcount};      // 0x010: POPCOUNT
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
