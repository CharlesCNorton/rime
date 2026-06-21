// CELL: Configurable Elementary Local Logic automaton
// 64-cell 1D cellular automaton. Configurable Wolfram rule byte (0-255).
// Wrapping boundary (cell 0's left neighbor is cell 63).
// Single-cycle step: all cells update simultaneously.
//
// Memory map:
//   0x000: STATE_LO (write/read) — cells [31:0]
//   0x004: STATE_HI (write/read) — cells [63:32]
//   0x008: RULE     (write/read) — 8-bit Wolfram rule number
//   0x00C: CONTROL  (write)      — bit 0 = step one generation, bit 1 = reset
//   0x010: GEN      (read)       — generation counter
//   0x014: ALIVE    (read)       — popcount of living cells

// `cell` is a reserved SystemVerilog keyword (config blocks), so the module
// is named cell_mod with a manifest top_module override — same convention
// as wire/wire_mod.
module cell_mod (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [63:0] state;
    logic [7:0]  rule;
    logic [31:0] gen_count;

    // Compute next state for all 64 cells simultaneously
    function automatic [63:0] step_all(input [63:0] s, input [7:0] r);
        logic [63:0] next;
        for (integer i = 0; i < 64; i = i + 1) begin
            logic left, center, right;
            logic [2:0] neighborhood;
            left   = s[(i + 63) % 64];
            center = s[i];
            right  = s[(i + 1) % 64];
            neighborhood = {left, center, right};
            next[i] = r[neighborhood];
        end
        step_all = next;
    endfunction

    // Popcount for alive cells
    function automatic [6:0] popcount64(input [63:0] v);
        integer j;
        popcount64 = 0;
        for (j = 0; j < 64; j = j + 1)
            popcount64 = popcount64 + {6'd0, v[j]};
    endfunction

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            state     <= 64'd0;
            rule      <= 8'd0;
            gen_count <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: state[31:0]  <= reg_wdata;
                    3'h1: state[63:32] <= reg_wdata;
                    3'h2: rule <= reg_wdata[7:0];
                    3'h3: begin
                        if (reg_wdata[1]) begin
                            state     <= 64'd0;
                            gen_count <= 32'd0;
                        end
                        if (reg_wdata[0]) begin
                            state     <= step_all(state, rule);
                            gen_count <= gen_count + 32'd1;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= state[31:0];
                    3'h1: reg_rdata <= state[63:32];
                    3'h2: reg_rdata <= {24'd0, rule};
                    3'h4: reg_rdata <= gen_count;
                    3'h5: reg_rdata <= {25'd0, popcount64(state)};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
