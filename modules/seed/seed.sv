// SEED: Secure Entropy-Enhanced Derivation
// Nonce generator: monotonic 32-bit counter XOR-mixed with a seed value
// through a simple FNV-1a-style hash. Each GENERATE reads the counter,
// mixes it with the seed, increments the counter, and latches the result.
// The counter never repeats (wraps at 2^32). The seed can be loaded
// from external entropy (e.g. EMBERLITE).
//
// Memory map:
//   0x000: SEED_VAL (write) — 32-bit entropy seed
//   0x004: NONCE    (read)  — last generated nonce
//   0x008: COUNTER  (read)  — current counter value (pre-increment)
//   0x00C: CONTROL  (write) — bit 0 = generate, bit 1 = reset counter
//   0x010: STATUS   (read)  — bit 0 = nonce valid (at least one generated)

module seed (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] seed_val;
    logic [31:0] counter;
    logic [31:0] nonce;
    logic        valid;

    // FNV-1a-style mix expanded as explicit wires
    localparam [31:0] FNV_BASIS = 32'h811C9DC5;

    wire [31:0] inner_x = FNV_BASIS ^ seed_val;
    wire [31:0] inner_t1 = inner_x + (inner_x << 1);
    wire [31:0] inner_t2 = inner_t1 + (inner_x << 4);
    wire [31:0] inner_t3 = inner_t2 + (inner_x << 7);
    wire [31:0] inner_t4 = inner_t3 + (inner_x << 8);
    wire [31:0] inner_y  = inner_t4 + (inner_x << 24);

    wire [31:0] outer_x = inner_y ^ counter;
    wire [31:0] outer_t1 = outer_x + (outer_x << 1);
    wire [31:0] outer_t2 = outer_t1 + (outer_x << 4);
    wire [31:0] outer_t3 = outer_t2 + (outer_x << 7);
    wire [31:0] outer_t4 = outer_t3 + (outer_x << 8);
    wire [31:0] next_nonce = outer_t4 + (outer_x << 24);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            seed_val <= 32'd0;
            counter  <= 32'd0;
            nonce    <= 32'd0;
            valid    <= 1'b0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        seed_val <= reg_wdata;
                        valid    <= 1'b0;  // counter stays monotonic across reseeds
                    end
                    3'h3: begin
                        if (reg_wdata[1]) begin
                            counter <= 32'd0;
                            valid   <= 1'b0;
                        end
                        if (reg_wdata[0]) begin
                            nonce   <= next_nonce;
                            counter <= counter + 32'd1;
                            valid   <= 1'b1;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= seed_val;
                    3'h1: reg_rdata <= nonce;
                    3'h2: reg_rdata <= counter;
                    3'h4: reg_rdata <= {31'd0, valid};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
