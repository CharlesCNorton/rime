// rime_i_core: RV32I soft CPU for the RIME compositor system.
//
// Multi-cycle implementation: 5-state FSM (FETCH, DECODE, EXECUTE,
// MEM_WAIT, WRITEBACK). Supports the full RV32I base integer ISA
// (37 instructions + FENCE). No interrupts, no CSRs, no M extension.
//
// Memory interface:
//   mem_addr   — 32-bit byte address
//   mem_wdata  — 32-bit write data
//   mem_wstrb  — 4-bit byte enables (0000 = read, nonzero = write)
//   mem_valid  — request active
//   mem_rdata  — 32-bit read data from memory
//   mem_ready  — memory acknowledges the transaction
//
// Memory map (defined by the compositor top.sv, not this module):
//   0x00000000 — BRAM (firmware, 14 KB default)
//   0x20000000 — UART (TX, busy, RX, pending)
//   0x30000000-0x3F000000 — compositor module address regions
//
// The SRA instruction uses an explicit sign-extension mask because
// $signed() >>> shamt has a history of miscompiling for ECP5.
// See Known Limitations in README.md.

module rime_i_core (
    input  wire        clk,
    input  wire        rst,

    output logic [31:0] mem_addr,
    output logic [31:0] mem_wdata,
    output logic [3:0]  mem_wstrb,
    output logic        mem_valid,
    input  wire  [31:0] mem_rdata,
    input  wire         mem_ready,

    output wire [31:0] dbg_reg10
);

    localparam [2:0] S_FETCH    = 3'd0;
    localparam [2:0] S_DECODE   = 3'd1;
    localparam [2:0] S_EXECUTE  = 3'd2;
    localparam [2:0] S_MEM_WAIT = 3'd3;
    localparam [2:0] S_WRITEBACK = 3'd4;

    (* keep *) logic [2:0]  state;
    (* keep *) logic [31:0] pc;
    (* keep *) logic [31:0] instr;

    logic [31:0] regs [0:31];
    assign dbg_reg10 = regs[10];

    wire [6:0]  opcode = instr[6:0];
    wire [4:0]  rd     = instr[11:7];
    wire [2:0]  funct3 = instr[14:12];
    wire [4:0]  rs1    = instr[19:15];
    wire [4:0]  rs2    = instr[24:20];
    wire [6:0]  funct7 = instr[31:25];

    wire [31:0] rs1_val = (rs1 == 5'd0) ? 32'd0 : regs[rs1];
    wire [31:0] rs2_val = (rs2 == 5'd0) ? 32'd0 : regs[rs2];

    wire [31:0] imm_i = {{20{instr[31]}}, instr[31:20]};
    wire [31:0] imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
    wire [31:0] store_addr = rs1_val + imm_s;
    wire [31:0] imm_b = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
    wire [31:0] imm_u = {instr[31:12], 12'd0};
    wire [31:0] imm_j = {{11{instr[31]}}, instr[31], instr[19:12], instr[20], instr[30:21], 1'b0};

    localparam [6:0] OP_LUI    = 7'b0110111;
    localparam [6:0] OP_AUIPC  = 7'b0010111;
    localparam [6:0] OP_JAL    = 7'b1101111;
    localparam [6:0] OP_JALR   = 7'b1100111;
    localparam [6:0] OP_BRANCH = 7'b1100011;
    localparam [6:0] OP_LOAD   = 7'b0000011;
    localparam [6:0] OP_STORE  = 7'b0100011;
    localparam [6:0] OP_ALUI   = 7'b0010011;
    localparam [6:0] OP_ALU    = 7'b0110011;
    localparam [6:0] OP_FENCE  = 7'b0001111;
    localparam [6:0] OP_SYSTEM = 7'b1110011;

    logic [31:0] alu_result;
    logic [31:0] wb_data;
    logic        wb_en;
    (* keep *) logic [31:0] next_pc;
    logic        is_load;

    wire [31:0] alu_b = (opcode == OP_ALU) ? rs2_val : imm_i;
    wire        alu_sub = (opcode == OP_ALU) && funct7[5] && (funct3 == 3'b000);
    wire [4:0]  shamt = alu_b[4:0];

    always_comb begin
        case (funct3)
            3'b000: alu_result = alu_sub ? (rs1_val - alu_b) : (rs1_val + alu_b);
            3'b001: alu_result = rs1_val << shamt;
            3'b010: alu_result = {31'd0, $signed(rs1_val) < $signed(alu_b)};
            3'b011: alu_result = {31'd0, rs1_val < alu_b};
            3'b100: alu_result = rs1_val ^ alu_b;
            3'b101: begin
                logic [31:0] sra_mask;
                sra_mask = (shamt == 5'd0) ? 32'd0 : ({32{rs1_val[31]}} << (6'd32 - {1'b0, shamt}));
                alu_result = funct7[5] ? ((rs1_val >> shamt) | sra_mask) : (rs1_val >> shamt);
            end
            3'b110: alu_result = rs1_val | alu_b;
            3'b111: alu_result = rs1_val & alu_b;
        endcase
    end

    logic branch_taken;
    always_comb begin
        case (funct3)
            3'b000: branch_taken = (rs1_val == rs2_val);
            3'b001: branch_taken = (rs1_val != rs2_val);
            3'b100: branch_taken = ($signed(rs1_val) < $signed(rs2_val));
            3'b101: branch_taken = ($signed(rs1_val) >= $signed(rs2_val));
            3'b110: branch_taken = (rs1_val < rs2_val);
            3'b111: branch_taken = (rs1_val >= rs2_val);
            default: branch_taken = 1'b0;
        endcase
    end

    logic [31:0] load_data;
    wire [1:0] byte_offset = mem_addr[1:0];
    always_comb begin
        case (funct3)
            3'b000: begin
                case (byte_offset)
                    2'd0: load_data = {{24{mem_rdata[7]}},  mem_rdata[7:0]};
                    2'd1: load_data = {{24{mem_rdata[15]}}, mem_rdata[15:8]};
                    2'd2: load_data = {{24{mem_rdata[23]}}, mem_rdata[23:16]};
                    2'd3: load_data = {{24{mem_rdata[31]}}, mem_rdata[31:24]};
                endcase
            end
            3'b001: load_data = byte_offset[1] ? {{16{mem_rdata[31]}}, mem_rdata[31:16]}
                                                : {{16{mem_rdata[15]}}, mem_rdata[15:0]};
            3'b010: load_data = mem_rdata;
            3'b100: begin
                case (byte_offset)
                    2'd0: load_data = {24'd0, mem_rdata[7:0]};
                    2'd1: load_data = {24'd0, mem_rdata[15:8]};
                    2'd2: load_data = {24'd0, mem_rdata[23:16]};
                    2'd3: load_data = {24'd0, mem_rdata[31:24]};
                endcase
            end
            3'b101: load_data = byte_offset[1] ? {16'd0, mem_rdata[31:16]}
                                                : {16'd0, mem_rdata[15:0]};
            default: load_data = mem_rdata;
        endcase
    end

    integer i;
    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= S_FETCH;
            pc        <= 32'd0;
            mem_valid <= 1'b0;
            mem_wstrb <= 4'b0000;
            for (i = 0; i < 32; i = i + 1)
                regs[i] <= 32'd0;
        end else begin
            mem_valid <= 1'b0;
            case (state)
                S_FETCH: begin
                    mem_addr  <= pc;
                    mem_wstrb <= 4'b0000;
                    mem_valid <= 1'b1;
                    state     <= S_DECODE;
                end

                S_DECODE: begin
                    if (mem_ready) begin
                        instr <= mem_rdata;
                        state <= S_EXECUTE;
                    end else begin
                        mem_valid <= 1'b1;
                    end
                end

                S_EXECUTE: begin
                    is_load <= 1'b0;
                    wb_en   <= 1'b0;
                    next_pc <= pc + 32'd4;

                    case (opcode)
                        OP_LUI: begin
                            wb_data <= imm_u;
                            wb_en   <= (rd != 5'd0);
                            state   <= S_WRITEBACK;
                        end
                        OP_AUIPC: begin
                            wb_data <= pc + imm_u;
                            wb_en   <= (rd != 5'd0);
                            state   <= S_WRITEBACK;
                        end
                        OP_JAL: begin
                            wb_data <= pc + 32'd4;
                            wb_en   <= (rd != 5'd0);
                            next_pc <= pc + imm_j;
                            state   <= S_WRITEBACK;
                        end
                        OP_JALR: begin
                            wb_data <= pc + 32'd4;
                            wb_en   <= (rd != 5'd0);
                            next_pc <= (rs1_val + imm_i) & 32'hFFFFFFFE;
                            state   <= S_WRITEBACK;
                        end
                        OP_BRANCH: begin
                            if (branch_taken)
                                next_pc <= pc + imm_b;
                            pc    <= branch_taken ? (pc + imm_b) : (pc + 32'd4);
                            state <= S_FETCH;
                        end
                        OP_LOAD: begin
                            mem_addr  <= rs1_val + imm_i;
                            mem_wstrb <= 4'b0000;
                            mem_valid <= 1'b1;
                            is_load   <= 1'b1;
                            state     <= S_MEM_WAIT;
                        end
                        OP_STORE: begin
                            mem_addr <= store_addr;
                            case (funct3)
                                3'b000: begin
                                    mem_wdata <= {4{rs2_val[7:0]}};
                                    mem_wstrb <= 4'b0001 << store_addr[1:0];
                                end
                                3'b001: begin
                                    mem_wdata <= {2{rs2_val[15:0]}};
                                    mem_wstrb <= store_addr[1] ? 4'b1100 : 4'b0011;
                                end
                                3'b010: begin
                                    mem_wdata <= rs2_val;
                                    mem_wstrb <= 4'b1111;
                                end
                                default: mem_wstrb <= 4'b0000;
                            endcase
                            mem_valid <= 1'b1;
                            state     <= S_MEM_WAIT;
                        end
                        OP_ALUI, OP_ALU: begin
                            wb_data <= alu_result;
                            wb_en   <= (rd != 5'd0);
                            state   <= S_WRITEBACK;
                        end
                        OP_FENCE: begin
                            state <= S_WRITEBACK;
                        end
                        OP_SYSTEM: begin
                            state <= S_WRITEBACK;
                        end
                        default: begin
                            state <= S_WRITEBACK;
                        end
                    endcase
                end

                S_MEM_WAIT: begin
                    if (mem_ready) begin
                        if (is_load) begin
                            wb_data <= load_data;
                            wb_en   <= (rd != 5'd0);
                            state   <= S_WRITEBACK;
                        end else begin
                            pc    <= pc + 32'd4;
                            state <= S_FETCH;
                        end
                    end else begin
                        mem_valid <= 1'b1;
                    end
                end

                S_WRITEBACK: begin
                    if (wb_en)
                        regs[rd] <= wb_data;
                    pc    <= next_pc;
                    state <= S_FETCH;
                end

                default: state <= S_FETCH;
            endcase
        end
    end
endmodule
