// AUGUR: Autonomous Uncertainty Generator for Universal Reasoning
// MCMC (Markov Chain Monte Carlo) sampler with 4 parallel chains.
// Each chain does a Metropolis-Hastings random walk: propose a new
// state by adding LFSR noise, accept/reject based on an energy function.
//
// Memory map:
//   0x000: CHAIN0 (read) — current state of chain 0 (16-bit)
//   0x004: CHAIN1 (read)
//   0x008: CHAIN2 (read)
//   0x00C: CHAIN3 (read)
//   0x010: CONTROL (write) — bit 0 = step all chains, bit 1 = reset
//   0x014: STEPS   (read) — total steps taken
//   0x018: ACCEPTS (read) — total accepted proposals
//   0x01C: MEAN    (read) — mean of all 4 chains (approximation)
//   0x020: TARGET  (write) — target value for the energy function

module augur (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // 4 parallel MCMC chains
    logic signed [15:0] chain [0:3];
    logic [15:0] step_count;
    logic [15:0] accept_count;
    logic signed [15:0] target;

    // 4 independent LFSRs for proposal noise
    logic [15:0] lfsr [0:3];

    // Energy function: |x - target|^2 (quadratic, peaks at target)
    function automatic [31:0] energy(input signed [15:0] x, input signed [15:0] tgt);
        logic signed [15:0] diff;
        diff = x - tgt;
        energy = diff * diff;
    endfunction

    // Combinational proposals and accept decisions
    wire signed [15:0] proposal [0:3];
    wire [31:0] e_current [0:3];
    wire [31:0] e_proposal [0:3];
    wire accept [0:3];

    genvar gi;
    generate
        for (gi = 0; gi < 4; gi = gi + 1) begin : mcmc
            assign proposal[gi] = chain[gi] + {{12{lfsr[gi][15]}}, lfsr[gi][15:12]};
            assign e_current[gi] = energy(chain[gi], target);
            assign e_proposal[gi] = energy(proposal[gi], target);
            assign accept[gi] = (e_proposal[gi] <= e_current[gi]);
        end
    endgenerate

    integer _i;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            chain[0] <= 16'sd0;
            chain[1] <= 16'sd100;
            chain[2] <= -16'sd100;
            chain[3] <= 16'sd50;
            lfsr[0]  <= 16'hACE1;
            lfsr[1]  <= 16'h1337;
            lfsr[2]  <= 16'hBEEF;
            lfsr[3]  <= 16'hCAFE;
            step_count  <= 16'd0;
            accept_count <= 16'd0;
            target <= 16'sd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h4: begin // CONTROL
                        if (reg_wdata[0]) begin
                            for (_i = 0; _i < 4; _i = _i + 1) begin
                                lfsr[_i] <= {lfsr[_i][14:0], lfsr[_i][15] ^ lfsr[_i][14] ^ lfsr[_i][12] ^ lfsr[_i][3]};
                                if (accept[_i]) begin
                                    chain[_i] <= proposal[_i];
                                    accept_count <= accept_count + 16'd1;
                                end
                            end
                            step_count <= step_count + 16'd1;
                        end
                        if (reg_wdata[1]) begin
                            chain[0] <= 16'sd0;
                            chain[1] <= 16'sd100;
                            chain[2] <= -16'sd100;
                            chain[3] <= 16'sd50;
                            step_count <= 16'd0;
                            accept_count <= 16'd0;
                        end
                    end
                    3'h0: target <= reg_wdata[15:0]; // TARGET at 0x020... wait
                endcase
                // TARGET at 0x020
                if (reg_addr[5:2] == 4'h8)
                    target <= reg_wdata[15:0];
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {{16{chain[0][15]}}, chain[0]};
                    3'h1: reg_rdata <= {{16{chain[1][15]}}, chain[1]};
                    3'h2: reg_rdata <= {{16{chain[2][15]}}, chain[2]};
                    3'h3: reg_rdata <= {{16{chain[3][15]}}, chain[3]};
                    3'h4: reg_rdata <= 32'd0;
                    3'h5: reg_rdata <= {16'd0, step_count};
                    3'h6: reg_rdata <= {16'd0, accept_count};
                    3'h7: begin // MEAN
                        logic signed [17:0] sum;
                        sum = {{2{chain[0][15]}}, chain[0]} + {{2{chain[1][15]}}, chain[1]} +
                              {{2{chain[2][15]}}, chain[2]} + {{2{chain[3][15]}}, chain[3]};
                        reg_rdata <= {{16{sum[17]}}, sum[17:2]}; // divide by 4
                    end
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
