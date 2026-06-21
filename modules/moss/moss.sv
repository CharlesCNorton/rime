// MOSS: Massively Orchestrated Spatial Stepper
// 8x8 cellular automaton (Game of Life rules).
// All 64 cells update simultaneously each step.
//
// Memory map:
//   0x000: ROW0-ROW7 (write/read) — 8 rows × 8 bits = 64-cell grid
//          ROW[n] at offset n*4, bits [7:0] = cells in that row
//   0x020: CONTROL (write) — bit 0 = step one generation, bit 1 = clear
//   0x024: GEN     (read)  — generation counter
//   0x028: ALIVE   (read)  — number of live cells

module moss (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // 64-bit flat grid: bit [r*8+c] = cell at (r,c)
    logic [63:0] grid;
    logic [15:0] gen_count;

    // Access helper
    `define CELL(g, r, c) g[((r)&3'h7)*8 + ((c)&3'h7)]

    // Compute next generation combinationally
    logic [63:0] next_grid;
    integer _r, _c, _n;
    always_comb begin
        next_grid = 64'd0;
        for (_r = 0; _r < 8; _r = _r + 1)
            for (_c = 0; _c < 8; _c = _c + 1) begin
                _n = 0;
                _n = _n + grid[((_r-1)&7)*8 + ((_c-1)&7)];
                _n = _n + grid[((_r-1)&7)*8 + _c];
                _n = _n + grid[((_r-1)&7)*8 + ((_c+1)&7)];
                _n = _n + grid[_r*8 + ((_c-1)&7)];
                _n = _n + grid[_r*8 + ((_c+1)&7)];
                _n = _n + grid[((_r+1)&7)*8 + ((_c-1)&7)];
                _n = _n + grid[((_r+1)&7)*8 + _c];
                _n = _n + grid[((_r+1)&7)*8 + ((_c+1)&7)];
                if (grid[_r*8+_c])
                    next_grid[_r*8+_c] = (_n == 2 || _n == 3) ? 1'b1 : 1'b0;
                else
                    next_grid[_r*8+_c] = (_n == 3) ? 1'b1 : 1'b0;
            end
    end

    // Alive count
    logic [6:0] alive;
    always_comb begin
        alive = 7'd0;
        for (_r = 0; _r < 64; _r = _r + 1)
            alive = alive + {6'd0, grid[_r]};
    end

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            grid <= 64'd0;
            gen_count <= 16'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[5] == 1'b0) begin
                    // 0x000-0x01C: write grid rows
                    case (reg_addr[4:2])
                        3'd0: grid[7:0]   <= reg_wdata[7:0];
                        3'd1: grid[15:8]  <= reg_wdata[7:0];
                        3'd2: grid[23:16] <= reg_wdata[7:0];
                        3'd3: grid[31:24] <= reg_wdata[7:0];
                        3'd4: grid[39:32] <= reg_wdata[7:0];
                        3'd5: grid[47:40] <= reg_wdata[7:0];
                        3'd6: grid[55:48] <= reg_wdata[7:0];
                        3'd7: grid[63:56] <= reg_wdata[7:0];
                    endcase
                end else begin
                    case (reg_addr[4:2])
                        3'h0: begin
                            if (reg_wdata[0]) begin
                                grid <= next_grid;
                                gen_count <= gen_count + 16'd1;
                            end
                            if (reg_wdata[1]) begin
                                grid <= 64'd0;
                                gen_count <= 16'd0;
                            end
                        end
                    endcase
                end
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[5] == 1'b0) begin
                    case (reg_addr[4:2])
                        3'd0: reg_rdata <= {24'd0, grid[7:0]};
                        3'd1: reg_rdata <= {24'd0, grid[15:8]};
                        3'd2: reg_rdata <= {24'd0, grid[23:16]};
                        3'd3: reg_rdata <= {24'd0, grid[31:24]};
                        3'd4: reg_rdata <= {24'd0, grid[39:32]};
                        3'd5: reg_rdata <= {24'd0, grid[47:40]};
                        3'd6: reg_rdata <= {24'd0, grid[55:48]};
                        3'd7: reg_rdata <= {24'd0, grid[63:56]};
                    endcase
                end else begin
                    case (reg_addr[4:2])
                        3'h0: reg_rdata <= 32'd0;
                        3'h1: reg_rdata <= {16'd0, gen_count};
                        3'h2: reg_rdata <= {25'd0, alive};
                        default: reg_rdata <= 32'd0;
                    endcase
                end
            end
        end
    end
endmodule
