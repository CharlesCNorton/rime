// DRUM: Microsequencer
// 16-entry instruction memory. Each instruction is 32 bits:
//   bits [31:28] = opcode (0=NOP, 1=OUT, 2=WAIT, 3=JMP, 4=HALT)
//   bits [27:0]  = operand (depends on opcode)
//
// OUT: writes operand[7:0] to OUTPUT_LATCH register
// WAIT: stalls for operand cycles
// JMP: branches to operand[3:0] (instruction index)
// HALT: stops execution
//
// Memory map:
//   0x000-0x03C: PROG[0..15] (write) — instruction memory
//   0x040: OUTPUT  (read)  — last OUT value
//   0x044: PC      (read)  — current program counter
//   0x048: STATUS  (read)  — bit 0 = running, bit 1 = halted
//   0x04C: CONTROL (write) — bit 0 = start, bit 1 = reset

module drum (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] prog [0:15];
    logic [3:0]  pc;
    logic        running;
    logic        halted;
    logic [27:0] wait_count;
    logic [7:0]  out_latch;

    wire [31:0] cur_instr = prog[pc];
    wire [3:0]  opcode    = cur_instr[31:28];
    wire [27:0] operand   = cur_instr[27:0];

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            for (integer i = 0; i < 16; i = i + 1) prog[i] <= 32'd0;
            pc <= 4'd0;
            running <= 1'b0;
            halted <= 1'b0;
            wait_count <= 28'd0;
            out_latch <= 8'd0;
        end else begin
            if (running && !halted) begin
                if (wait_count != 28'd0) begin
                    wait_count <= wait_count - 28'd1;
                end else begin
                    case (opcode)
                        4'd0: pc <= pc + 4'd1;          // NOP
                        4'd1: begin                      // OUT
                            out_latch <= operand[7:0];
                            pc <= pc + 4'd1;
                        end
                        4'd2: begin                      // WAIT
                            wait_count <= operand;
                            pc <= pc + 4'd1;
                        end
                        4'd3: pc <= operand[3:0];        // JMP
                        4'd4: begin                      // HALT
                            halted <= 1'b1;
                            running <= 1'b0;
                        end
                        default: pc <= pc + 4'd1;
                    endcase
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0) begin
                    prog[reg_addr[5:2]] <= reg_wdata;
                end else if (reg_addr[5:2] == 4'h3) begin
                    if (reg_wdata[1]) begin
                        pc <= 4'd0; running <= 1'b0; halted <= 1'b0;
                        wait_count <= 28'd0; out_latch <= 8'd0;
                    end
                    if (reg_wdata[0]) begin
                        pc <= 4'd0; running <= 1'b1; halted <= 1'b0;
                    end
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0) begin
                    reg_rdata <= prog[reg_addr[5:2]];
                end else case (reg_addr[5:2])
                    4'h0: reg_rdata <= {24'd0, out_latch};
                    4'h1: reg_rdata <= {28'd0, pc};
                    4'h2: reg_rdata <= {30'd0, halted, running};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
