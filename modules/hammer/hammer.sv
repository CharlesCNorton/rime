// HAMMER: Hardware Accelerated Matching and Measurement Engine Register
// 256-bit Hamming distance: popcount(A XOR B).
// Two 256-bit vectors loaded via 8 x 32-bit writes each.
// Distance available combinationally after load.
//
// Memory map:
//   0x000-0x01C: A[0..7]   (write) — 256-bit vector A
//   0x020-0x03C: B[0..7]   (write) — 256-bit vector B
//   0x040: DISTANCE  (read)  — 9-bit Hamming distance (0-256)
//   0x044: MATCH     (read)  — 1 if distance == 0
//   0x048: THRESHOLD (write) — fuzzy match threshold
//   0x04C: FUZZY     (read)  — 1 if distance <= threshold

module hammer (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    logic [31:0] a_reg [0:7];
    logic [31:0] b_reg [0:7];
    logic [8:0]  threshold;

    // XOR all 8 word pairs
    wire [31:0] xor_w [0:7];
    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : gen_xor
            assign xor_w[gi] = a_reg[gi] ^ b_reg[gi];
        end
    endgenerate

    // Popcount each 32-bit word using an adder tree
    function automatic [5:0] pop32(input [31:0] v);
        integer k;
        reg [5:0] c;
        begin
            c = 0;
            for (k = 0; k < 32; k = k + 1)
                c = c + {5'd0, v[k]};
            pop32 = c;
        end
    endfunction

    wire [5:0] pc [0:7];
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : gen_pop
            assign pc[gi] = pop32(xor_w[gi]);
        end
    endgenerate

    wire [8:0] distance = {3'd0, pc[0]} + {3'd0, pc[1]} + {3'd0, pc[2]} + {3'd0, pc[3]}
                        + {3'd0, pc[4]} + {3'd0, pc[5]} + {3'd0, pc[6]} + {3'd0, pc[7]};

    integer _i;
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            threshold <= 9'd0;
            for (_i = 0; _i < 8; _i = _i + 1) begin
                a_reg[_i] <= 32'd0;
                b_reg[_i] <= 32'd0;
            end
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b0)
                    a_reg[reg_addr[4:2]] <= reg_wdata;
                else if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b1)
                    b_reg[reg_addr[4:2]] <= reg_wdata;
                else if (reg_addr[6:2] == 5'h12)
                    threshold <= reg_wdata[8:0];
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[6:2])
                    5'h10: reg_rdata <= {23'd0, distance};
                    5'h11: reg_rdata <= {31'd0, distance == 9'd0 ? 1'b1 : 1'b0};
                    5'h13: reg_rdata <= {31'd0, distance <= threshold ? 1'b1 : 1'b0};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
