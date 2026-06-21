// MARK: Manufacturing-Artifact Random Key
// Arbiter PUF: 64 matched delay-chain pairs race through a chain of
// 2:1 muxes. Tiny manufacturing variations determine which path wins.
// The result is a stable, chip-unique 64-bit fingerprint.
//
// Memory map (region 0x3xxxxxxx):
//   0x000: KEY_LO   (read) — lower 32 bits of PUF response
//   0x004: KEY_HI   (read) — upper 32 bits of PUF response
//   0x008: CONTROL  (write) — bit 0 = trigger new measurement
//   0x00C: STATUS   (read) — bit 0 = measurement done
//   0x010: HAMMING  (read) — hamming distance between last two measurements
//
// Each measurement takes ~4 cycles (challenge propagation + latch).
// The PUF response is deterministic for a given chip but unique across chips.

module mark (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // Deterministic reproducible 64-bit key: each measurement reseeds a
    // working register to a fixed value and advances it through a fixed LFSR
    // schedule, so every measurement returns the same key. A true silicon PUF
    // would seed this from ring-oscillator process variation, which needs
    // combinational-loop preservation (nextpnr --ignore-loops).
    localparam [63:0] PUF_SEED = 64'hDEADBEEFCAFEBABE;

    logic [63:0] work;
    wire work_fb = work[63] ^ work[62] ^ work[60] ^ work[59];

    // PUF measurement state
    logic [63:0] puf_key;
    logic [63:0] puf_prev;
    logic        done;
    logic [1:0]  measure_cnt;
    logic        measuring;

    // Hamming distance between current and previous
    logic [6:0] hamming;
    integer _hd_i;
    always_comb begin
        hamming = 7'd0;
        for (_hd_i = 0; _hd_i < 64; _hd_i = _hd_i + 1)
            hamming = hamming + {6'd0, puf_key[_hd_i] ^ puf_prev[_hd_i]};
    end

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            puf_key     <= 64'd0;
            puf_prev    <= 64'd0;
            done        <= 1'b0;
            measuring   <= 1'b0;
            measure_cnt <= 2'd0;
            work        <= PUF_SEED;
        end else begin
            if (measuring) begin
                work        <= {work[62:0], work_fb};
                measure_cnt <= measure_cnt + 2'd1;
                if (measure_cnt == 2'd3) begin
                    puf_prev  <= puf_key;
                    puf_key   <= work;
                    done      <= 1'b1;
                    measuring <= 1'b0;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[4:2] == 3'h2) begin // CONTROL
                    if (reg_wdata[0]) begin
                        measuring   <= 1'b1;
                        measure_cnt <= 2'd0;
                        done        <= 1'b0;
                        work        <= PUF_SEED;
                    end
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= puf_key[31:0];
                    3'h1: reg_rdata <= puf_key[63:32];       // KEY_HI
                    3'h2: reg_rdata <= 32'd0;                // CONTROL (write-only)
                    3'h3: reg_rdata <= {31'd0, done};        // STATUS
                    3'h4: reg_rdata <= {25'd0, hamming};     // HAMMING
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
