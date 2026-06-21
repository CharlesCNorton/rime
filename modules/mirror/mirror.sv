// MIRROR: Memory Indexing and Rapid Resolution Object Router
// 16-entry masked pseudo-TCAM. Parallel XOR-match with priority encoder.
// Each entry: 32-bit key, 32-bit mask, 32-bit value, 1-bit valid.
// Query: match = ((query ^ key) & mask) == 0. Lowest-index match wins.
//
// Memory map:
//   0x000: QUERY    (write) — 32-bit search key, triggers parallel lookup
//   0x004: RESULT   (read)  — matched value (0 if no match)
//   0x008: HIT      (read)  — bit 0 = match found, bits [7:4] = matched index
//   0x00C: COUNT    (read)  — number of valid entries
//   0x010: CONTROL  (write) — bit 0 = clear all entries
//   0x100-0x13C: KEY[0..15]   (write)
//   0x140-0x17C: MASK[0..15]  (write) — 1 = compare, 0 = wildcard
//   0x180-0x1BC: VALUE[0..15] (write)
//   0x1C0-0x1FC: VALID[0..15] (write) — bit 0 = entry active

module mirror (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    localparam ENTRIES = 16;

    logic [31:0] keys  [0:ENTRIES-1];
    logic [31:0] masks [0:ENTRIES-1];
    logic [31:0] vals  [0:ENTRIES-1];
    logic        valids[0:ENTRIES-1];

    logic [31:0] query_reg;
    logic [31:0] result_reg;
    logic [3:0]  match_idx;
    logic        match_found;

    // Combinational parallel match
    wire [ENTRIES-1:0] match_vec;
    genvar gi;
    generate
        for (gi = 0; gi < ENTRIES; gi = gi + 1) begin : gen_match
            assign match_vec[gi] = valids[gi] && (((query_reg ^ keys[gi]) & masks[gi]) == 32'd0);
        end
    endgenerate

    // Priority encoder: lowest-index match
    reg [3:0]  pri_idx;
    reg        pri_found;
    integer _pi;
    always_comb begin
        pri_found = 1'b0;
        pri_idx = 4'd0;
        for (_pi = ENTRIES - 1; _pi >= 0; _pi = _pi - 1) begin
            if (match_vec[_pi]) begin
                pri_found = 1'b1;
                pri_idx = _pi[3:0];
            end
        end
    end

    // Count valid entries
    reg [4:0] valid_count;
    integer _vc;
    always_comb begin
        valid_count = 5'd0;
        for (_vc = 0; _vc < ENTRIES; _vc = _vc + 1)
            valid_count = valid_count + {4'd0, valids[_vc]};
    end

    integer _i;
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            query_reg <= 32'd0; result_reg <= 32'd0;
            match_idx <= 4'd0; match_found <= 1'b0;
            for (_i = 0; _i < ENTRIES; _i = _i + 1) begin
                keys[_i] <= 32'd0; masks[_i] <= 32'hFFFFFFFF;
                vals[_i] <= 32'd0; valids[_i] <= 1'b0;
            end
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:8] == 4'h0 && reg_addr[7:2] == 6'h00) begin
                    query_reg <= reg_wdata;
                end
                if (reg_addr[11:8] == 4'h0 && reg_addr[7:2] == 6'h04) begin
                    // 0x010: CONTROL — bit 0 clears all entries
                    if (reg_wdata[0]) begin
                        for (_i = 0; _i < ENTRIES; _i = _i + 1)
                            valids[_i] <= 1'b0;
                        query_reg <= 32'd0;
                    end
                end
                if (reg_addr[11:8] == 4'h1) begin
                    case (reg_addr[7:6])
                        2'b00: keys [reg_addr[5:2]] <= reg_wdata;
                        2'b01: masks[reg_addr[5:2]] <= reg_wdata;
                        2'b10: vals [reg_addr[5:2]] <= reg_wdata;
                        2'b11: valids[reg_addr[5:2]] <= reg_wdata[0];
                    endcase
                end
            end

            // Latch match result (one cycle after query write)
            match_found <= pri_found;
            match_idx <= pri_idx;
            result_reg <= pri_found ? vals[pri_idx] : 32'd0;

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[7:2])
                    6'h01: reg_rdata <= result_reg;
                    6'h02: reg_rdata <= {24'd0, match_idx, 3'd0, match_found};
                    6'h03: reg_rdata <= {27'd0, valid_count};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
