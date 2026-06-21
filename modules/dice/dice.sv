// DICE: Density-Inferred Computation Engine
// Stochastic computing: numbers are probabilities in random bitstreams.
// Multiplication = AND gate. Addition = MUX. All single-cycle.
//
// Memory map (region 0x3xxxxxxx):
//   0x000: OP_A    (write) — operand A as 8-bit probability (0-255 = 0.0-1.0)
//   0x004: OP_B    (write) — operand B as 8-bit probability
//   0x008: RESULT  (read)  — stochastic multiply result (A * B / 256)
//   0x00C: CONTROL (write) — bit 0 = start computation, bit 1 = reset
//   0x010: STATUS  (read)  — bit 0 = done
//   0x014: ADD_RES (read)  — stochastic addition result ((A + B) / 2)
//   0x018: CYCLES  (read)  — number of stream cycles used (precision indicator)
//
// The engine runs N=256 stochastic cycles per computation.
// Each cycle: LFSR generates random bits, compare against operand to get
// stochastic bit, AND/MUX the bits, accumulate result.

module dice (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    localparam N = 256;  // stochastic stream length

    logic [7:0] op_a, op_b;
    logic [8:0] mul_acc;   // accumulator for multiplication (count of AND=1)
    logic [8:0] add_acc;   // accumulator for addition (count of MUX=1)
    logic [8:0] cycle;
    logic       running;
    logic       done;

    // Two independent LFSRs for generating random comparison thresholds
    logic [15:0] lfsr_a, lfsr_b;
    wire lfsr_a_fb = lfsr_a[15] ^ lfsr_a[14] ^ lfsr_a[12] ^ lfsr_a[3];
    wire lfsr_b_fb = lfsr_b[15] ^ lfsr_b[13] ^ lfsr_b[11] ^ lfsr_b[0];

    // Stochastic bits: compare LFSR output against operand
    wire bit_a = (lfsr_a[7:0] < op_a);
    wire bit_b = (lfsr_b[7:0] < op_b);

    // Stochastic multiplication: AND
    wire mul_bit = bit_a & bit_b;

    // Stochastic addition: MUX (select bit_a or bit_b based on another random bit)
    wire add_bit = lfsr_a[8] ? bit_b : bit_a;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            op_a    <= 8'd0;
            op_b    <= 8'd0;
            mul_acc <= 9'd0;
            add_acc <= 9'd0;
            cycle   <= 9'd0;
            running <= 1'b0;
            done    <= 1'b0;
            lfsr_a  <= 16'hACE1;
            lfsr_b  <= 16'h1337;
        end else begin
            if (running) begin
                lfsr_a <= {lfsr_a[14:0], lfsr_a_fb};
                lfsr_b <= {lfsr_b[14:0], lfsr_b_fb};
                mul_acc <= mul_acc + {8'd0, mul_bit};
                add_acc <= add_acc + {8'd0, add_bit};
                cycle <= cycle + 9'd1;
                if (cycle == N[8:0] - 9'd1) begin
                    running <= 1'b0;
                    done    <= 1'b1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: op_a <= reg_wdata[7:0];
                    3'h1: op_b <= reg_wdata[7:0];
                    3'h3: begin // CONTROL
                        if (reg_wdata[0]) begin
                            running <= 1'b1;
                            done    <= 1'b0;
                            cycle   <= 9'd0;
                            mul_acc <= 9'd0;
                            add_acc <= 9'd0;
                            lfsr_a  <= 16'hACE1;
                            lfsr_b  <= 16'h1337;
                        end
                        if (reg_wdata[1]) begin
                            done <= 1'b0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {24'd0, op_a};
                    3'h1: reg_rdata <= {24'd0, op_b};
                    3'h2: reg_rdata <= {23'd0, mul_acc};       // MUL result
                    3'h3: reg_rdata <= 32'd0;
                    3'h4: reg_rdata <= {31'd0, done};          // STATUS
                    3'h5: reg_rdata <= {23'd0, add_acc};       // ADD result
                    3'h6: reg_rdata <= {23'd0, cycle};         // CYCLES
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
