// CAIRN: Hardware stack machine coprocessor
// 16-deep 32-bit stack with Forth-style operations.
// All operations execute in one cycle.
//
// Memory map:
//   0x000: PUSH    (write) — push value onto stack
//   0x004: POP     (read)  — pop and return top of stack
//   0x008: PEEK    (read)  — read top without popping
//   0x00C: OP      (write) — execute operation on stack:
//          0 = NOP, 1 = DUP, 2 = SWAP, 3 = DROP, 4 = ADD, 5 = SUB,
//          6 = MUL (lower 32), 7 = AND, 8 = OR, 9 = XOR, 10 = NOT,
//          11 = LT (comparison), 12 = EQ
//   0x010: DEPTH   (read)  — current stack depth (0-16)
//   0x014: CONTROL (write) — bit 0 = clear stack

module cairn (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] stack [0:15];
    logic [4:0]  sp;  // 0 = empty, 16 = full

    wire [31:0] tos = (sp > 5'd0) ? stack[sp - 5'd1] : 32'd0;
    wire [31:0] nos = (sp > 5'd1) ? stack[sp - 5'd2] : 32'd0;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            sp <= 5'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin // PUSH
                        if (sp < 5'd16) begin
                            stack[sp] <= reg_wdata;
                            sp <= sp + 5'd1;
                        end
                    end
                    3'h3: begin // OP
                        case (reg_wdata[3:0])
                            4'd1: begin // DUP
                                if (sp > 5'd0 && sp < 5'd16) begin
                                    stack[sp] <= tos;
                                    sp <= sp + 5'd1;
                                end
                            end
                            4'd2: begin // SWAP
                                if (sp > 5'd1) begin
                                    stack[sp-5'd1] <= nos;
                                    stack[sp-5'd2] <= tos;
                                end
                            end
                            4'd3: begin // DROP
                                if (sp > 5'd0) sp <= sp - 5'd1;
                            end
                            4'd4: begin // ADD
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= nos + tos;
                                    sp <= sp - 5'd1;
                                end
                            end
                            4'd5: begin // SUB
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= nos - tos;
                                    sp <= sp - 5'd1;
                                end
                            end
                            4'd6: begin // MUL (lower 32 bits)
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= nos * tos;
                                    sp <= sp - 5'd1;
                                end
                            end
                            4'd7: begin // AND
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= nos & tos;
                                    sp <= sp - 5'd1;
                                end
                            end
                            4'd8: begin // OR
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= nos | tos;
                                    sp <= sp - 5'd1;
                                end
                            end
                            4'd9: begin // XOR
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= nos ^ tos;
                                    sp <= sp - 5'd1;
                                end
                            end
                            4'd10: begin // NOT
                                if (sp > 5'd0)
                                    stack[sp-5'd1] <= ~tos;
                            end
                            4'd11: begin // LT (nos < tos -> 1, else 0)
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= {31'd0, nos < tos};
                                    sp <= sp - 5'd1;
                                end
                            end
                            4'd12: begin // EQ
                                if (sp > 5'd1) begin
                                    stack[sp-5'd2] <= {31'd0, nos == tos};
                                    sp <= sp - 5'd1;
                                end
                            end
                        endcase
                    end
                    3'h5: begin // CONTROL
                        if (reg_wdata[0]) sp <= 5'd0;
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: begin // POP
                        reg_rdata <= tos;
                        if (sp > 5'd0) sp <= sp - 5'd1;
                    end
                    3'h2: reg_rdata <= tos;         // PEEK
                    3'h4: reg_rdata <= {27'd0, sp}; // DEPTH
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
