// tiny_interp: minimal register machine for program space enumeration.
//
// 6 opcodes, 8-bit accumulator A and register B, 3-bit PC.
// Programs are 6 instructions × 3 bits = 18 bits.
// Executes up to 256 steps. Halts when PC >= 6 (falls off end).
//
// ISA:
//   0: INC   A = (A + 1) & 0xFF
//   1: DEC   A = (A - 1) & 0xFF
//   2: SWP   A <-> B
//   3: ADD   A = (A + B) & 0xFF
//   4: XOR   A = A ^ B
//   5: JNZ   if A != 0: PC = 0, else PC++
//
// Output: value of A when halted. If the program loops for 256 steps
// without halting, done=1 with halted=0 (timeout).

module tiny_interp_c (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    input  wire [23:0] program,  // 8 instructions × 3 bits = 24 bits
    input  wire [7:0]  init_a,
    input  wire [7:0]  init_b,
    output logic [7:0] result,
    output logic       done,
    output logic       halted
);
    localparam integer MAX_STEPS = 256;
    localparam integer PROG_LEN = 8;

    logic [7:0]  a, b;
    logic [3:0]  pc;  // 4 bits for 0-8 range
    logic [8:0]  step;
    logic        running;

    // Variable part-select (program[pc*3 +: 3]) causes yosys synthesis issues.
    // Replaced with case-based mux.
    logic [2:0] opcode;
    always_comb begin
        case (pc)
            4'd0: opcode = program[2:0];
            4'd1: opcode = program[5:3];
            4'd2: opcode = program[8:6];
            4'd3: opcode = program[11:9];
            4'd4: opcode = program[14:12];
            4'd5: opcode = program[17:15];
            4'd6: opcode = program[20:18];
            4'd7: opcode = program[23:21];
            default: opcode = 3'd6;  // NOP (past end)
        endcase
    end

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            running <= 1'b0;
            a <= 8'd0; b <= 8'd0; pc <= 4'd0; step <= 9'd0;
            result <= 8'd0; halted <= 1'b0;
        end else if (start) begin
            running <= 1'b1;
            a <= init_a; b <= init_b; pc <= 4'd0; step <= 9'd0;
            halted <= 1'b0;
        end else if (running) begin
            if (pc >= PROG_LEN) begin
                result <= a;
                halted <= 1'b1;
                done <= 1'b1;
                running <= 1'b0;
            end else if (step >= MAX_STEPS) begin
                result <= a;
                halted <= 1'b0;
                done <= 1'b1;
                running <= 1'b0;
            end else begin
                step <= step + 9'd1;
                case (opcode)
                    3'd0: begin a <= a + 8'd1;            pc <= pc + 4'd1; end  // INC
                    3'd1: begin a <= {1'b0, a[7:1]};     pc <= pc + 4'd1; end  // SHR (lossy)
                    3'd2: begin a <= ~a;                  pc <= pc + 4'd1; end  // CPL (complement)
                    3'd3: begin a <= a + b;               pc <= pc + 4'd1; end  // ADD
                    3'd4: begin a <= a | b;               pc <= pc + 4'd1; end  // OR
                    3'd5: begin                                       // JNZ
                        if (a != 8'd0) pc <= 4'd0;
                        else           pc <= pc + 4'd1;
                    end
                    default: pc <= pc + 4'd1;  // NOP for opcodes 6-7
                endcase
            end
        end
    end
endmodule
