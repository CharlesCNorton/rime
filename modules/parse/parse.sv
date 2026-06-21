// PARSE: Pattern Automaton for Realtime Stream Evaluation
// Hardware NFA with 8 states for matching byte patterns.
// State configuration stored in packed registers for clean synthesis.
//
// Memory map:
//   0x000: INPUT   (write) — feed one byte to the NFA
//   0x004: STATUS  (read)  — bit 0 = any accept state active, bits [8:1] = state mask
//   0x008: CONTROL (write) — bit 0 = reset NFA state
//   0x00C: MATCHES (read)  — total accept-state hits since last reset
//   0x100+N*4: STATE_CFG[N] (write) — configure state N (0-7):
//              bits [7:0]   = match byte
//              bits [10:8]  = next state on match (0-7)
//              bits [13:11] = next state on no-match (7 = stay)
//              bit 14       = accept state flag
//              bit 15       = active-on-reset flag

module parse (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // Pack each state as a 16-bit config word
    logic [15:0] cfg [0:7];

    // Active state mask
    logic [7:0] active;
    logic [15:0] match_count;

    // Unpack config fields
    wire [7:0] cfg_match [0:7];
    wire [2:0] cfg_hit   [0:7];
    wire [2:0] cfg_miss  [0:7];
    wire       cfg_accept[0:7];
    wire       cfg_init  [0:7];

    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : unpack
            assign cfg_match[gi]  = cfg[gi][7:0];
            assign cfg_hit[gi]    = cfg[gi][10:8];
            assign cfg_miss[gi]   = cfg[gi][13:11];
            assign cfg_accept[gi] = cfg[gi][14];
            assign cfg_init[gi]   = cfg[gi][15];
        end
    endgenerate

    // NFA transition: compute next_active from current active + input byte
    wire [7:0] input_byte = reg_wdata[7:0];

    logic [7:0] next_active;
    logic       any_accept;

    // Per-state transition outputs (which state does each active state activate?)
    wire [2:0] dest [0:7];
    wire       is_match [0:7];

    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : trans
            assign is_match[gi] = (input_byte == cfg_match[gi]);
            assign dest[gi] = is_match[gi] ? cfg_hit[gi] :
                              (cfg_miss[gi] != 3'd7) ? cfg_miss[gi] : gi[2:0];
        end
    endgenerate

    // Combine: for each possible destination state, OR all sources that point to it
    integer _i, _j;
    always_comb begin
        next_active = 8'd0;
        any_accept = 1'b0;
        for (_j = 0; _j < 8; _j = _j + 1) begin
            for (_i = 0; _i < 8; _i = _i + 1) begin
                if (active[_i] && dest[_i] == _j[2:0])
                    next_active[_j] = 1'b1;
            end
        end
        for (_i = 0; _i < 8; _i = _i + 1)
            if (active[_i] && cfg_accept[_i])
                any_accept = 1'b1;
    end

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            for (_i = 0; _i < 8; _i = _i + 1)
                cfg[_i] <= {1'b0, 1'b0, 3'd7, 3'd0, 8'd0};  // miss=7(stay), no accept, no init
            cfg[0][15] <= 1'b1;  // state 0 is init
            active <= 8'h01;
            match_count <= 16'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:8] == 4'h0) begin
                    case (reg_addr[4:2])
                        3'h0: begin // INPUT
                            active <= next_active;
                            if (any_accept)
                                match_count <= match_count + 16'd1;
                        end
                        3'h2: begin // CONTROL reset
                            if (reg_wdata[0]) begin
                                for (_i = 0; _i < 8; _i = _i + 1)
                                    active[_i] <= cfg_init[_i];
                                match_count <= 16'd0;
                            end
                        end
                    endcase
                end else begin
                    // 0x100+: config write
                    cfg[reg_addr[4:2]] <= reg_wdata[15:0];
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {23'd0, active, any_accept};
                    3'h3: reg_rdata <= {16'd0, match_count};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
