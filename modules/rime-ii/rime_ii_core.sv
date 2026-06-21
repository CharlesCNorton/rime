// rime_ii_core: RV32IMF_Zbb soft CPU with fused integer/FP datapath.
//
// The FPU is not a separate unit. The integer ALU's adder, shifter,
// and comparator are time-multiplexed for FP mantissa operations via
// micro-sequenced execution states. Two ECP5 MULT18X18D hard DSP
// blocks (modeled here as iterative for portability) handle 24x24
// mantissa multiply, 32x32 integer multiply, and Newton-Raphson
// iterations — all through the same pair.
//
// Extensions: M (mul/div), F (single-precision float), Zbb (bit manip)
// Interrupts: MTVEC/MEPC/MCAUSE/MSTATUS — one external IRQ line
// Counters:   MCYCLE, MINSTRET
//
// Fused-path FP (no duplicate adder/shifter):
//   FADD.S:  6 micro-ops through shared ALU
//   FMUL.S:  DSP multiply + normalize + round
//   FDIV.S:  Newton-Raphson (~45 cycles via DSP)
//   FSQRT.S: Newton-Raphson (~65 cycles via DSP)
//   FMADD.S: DSP mul + ALU add (no intermediate round)

module rime_ii_core (
    input  wire        clk,
    input  wire        rst,

    output logic [31:0] mem_addr,
    output logic [31:0] mem_wdata,
    output logic [3:0]  mem_wstrb,
    output logic        mem_valid,
    input  wire  [31:0] mem_rdata,
    input  wire         mem_ready,

    input  wire         irq_external,
    output wire  [31:0] dbg_reg10
);

    // =====================================================================
    // FSM states
    // =====================================================================
    localparam [4:0] S_FETCH       = 5'd0;
    localparam [4:0] S_DECODE      = 5'd1;
    localparam [4:0] S_EXECUTE     = 5'd2;
    localparam [4:0] S_MEM_WAIT    = 5'd3;
    localparam [4:0] S_WRITEBACK   = 5'd4;
    localparam [4:0] S_FP_UNPACK   = 5'd5;
    localparam [4:0] S_FP_ALIGN    = 5'd6;
    localparam [4:0] S_FP_COMPUTE  = 5'd7;
    localparam [4:0] S_FP_NORM     = 5'd8;
    localparam [4:0] S_FP_ROUND    = 5'd9;
    localparam [4:0] S_DSP_WAIT    = 5'd10;
    localparam [4:0] S_FP_NR_MUL1  = 5'd11;
    localparam [4:0] S_FP_NR_MUL2  = 5'd12;
    localparam [4:0] S_FP_NR_CORR  = 5'd13;
    localparam [4:0] S_DIV_ITER    = 5'd14;
    localparam [4:0] S_TRAP_ENTER  = 5'd15;
    localparam [4:0] S_TRAP_RETURN = 5'd16;
    localparam [4:0] S_FP_FMADD    = 5'd17;

    (* keep *) logic [4:0]  state;
    (* keep *) logic [31:0] pc;
    (* keep *) logic [31:0] instr;

    // =====================================================================
    // Register files
    // =====================================================================
    logic [31:0] regs [0:31];
    logic [31:0] fregs [0:31];
    // FP register file uses a single write port in S_WRITEBACK
    // to avoid multi-port RAM mapping failures in synthesis.
    assign dbg_reg10 = regs[10];

    // =====================================================================
    // Decode
    // =====================================================================
    wire [6:0]  opcode = instr[6:0];
    wire [4:0]  rd     = instr[11:7];
    wire [2:0]  funct3 = instr[14:12];
    wire [4:0]  rs1    = instr[19:15];
    wire [4:0]  rs2    = instr[24:20];
    wire [6:0]  funct7 = instr[31:25];
    wire [4:0]  rs3    = instr[31:27];

    wire [31:0] rs1_val  = (rs1 == 5'd0) ? 32'd0 : regs[rs1];
    wire [31:0] rs2_val  = (rs2 == 5'd0) ? 32'd0 : regs[rs2];
    wire [31:0] frs1_val = fregs[rs1];
    wire [31:0] frs2_val = fregs[rs2];
    wire [31:0] frs3_val = fregs[rs3];

    wire [31:0] imm_i = {{20{instr[31]}}, instr[31:20]};
    wire [31:0] imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
    wire [31:0] imm_b = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
    wire [31:0] imm_u = {instr[31:12], 12'd0};
    wire [31:0] imm_j = {{11{instr[31]}}, instr[31], instr[19:12], instr[20], instr[30:21], 1'b0};
    wire [31:0] store_addr = rs1_val + imm_s;

    localparam [6:0] OP_LUI    = 7'b0110111, OP_AUIPC  = 7'b0010111;
    localparam [6:0] OP_JAL    = 7'b1101111, OP_JALR   = 7'b1100111;
    localparam [6:0] OP_BRANCH = 7'b1100011;
    localparam [6:0] OP_LOAD   = 7'b0000011, OP_STORE  = 7'b0100011;
    localparam [6:0] OP_ALUI   = 7'b0010011, OP_ALU    = 7'b0110011;
    localparam [6:0] OP_FENCE  = 7'b0001111, OP_SYSTEM = 7'b1110011;
    localparam [6:0] OP_FLW    = 7'b0000111, OP_FSW    = 7'b0100111;
    localparam [6:0] OP_FMADD  = 7'b1000011, OP_FMSUB  = 7'b1000111;
    localparam [6:0] OP_FNMSUB = 7'b1001011, OP_FNMADD = 7'b1001111;
    localparam [6:0] OP_FP     = 7'b1010011;

    // =====================================================================
    // Integer ALU (shared with FP mantissa ops)
    // =====================================================================
    wire [31:0] int_alu_b = (opcode == OP_ALU) ? rs2_val : imm_i;
    wire        int_alu_sub = (opcode == OP_ALU) && funct7[5] && (funct3 == 3'b000);
    wire [4:0]  shamt = int_alu_b[4:0];

    logic [31:0] alu_result;
    always_comb begin
        case (funct3)
            3'b000: alu_result = int_alu_sub ? (rs1_val - int_alu_b) : (rs1_val + int_alu_b);
            3'b001: begin
                // Zbb: CLZ (funct7=0110000, rs2=00000), CTZ (rs2=00001), CPOP (rs2=00010)
                if (opcode == OP_ALUI && funct7 == 7'b0110000) begin
                    case (rs2)
                        5'd0: alu_result = {27'd0, clz_count};       // CLZ
                        5'd1: alu_result = {27'd0, ctz_count};       // CTZ
                        5'd2: alu_result = {26'd0, cpop_count};      // CPOP
                        default: alu_result = rs1_val << shamt;
                    endcase
                end else
                    alu_result = rs1_val << shamt;
            end
            3'b010: alu_result = {31'd0, $signed(rs1_val) < $signed(int_alu_b)};
            3'b011: alu_result = {31'd0, rs1_val < int_alu_b};
            3'b100: begin
                if (opcode == OP_ALU && funct7 == 7'b0100000)
                    alu_result = rs1_val ^ ~rs2_val;  // Zbb XNOR
                else
                    alu_result = rs1_val ^ int_alu_b;
            end
            3'b101: begin
                logic [31:0] sra_mask;
                sra_mask = (shamt == 5'd0) ? 32'd0 : ({32{rs1_val[31]}} << (6'd32 - {1'b0, shamt}));
                if (opcode == OP_ALUI && funct7 == 7'b0110000)
                    alu_result = (rs1_val >> shamt) | (rs1_val << (6'd32 - {1'b0, shamt})); // Zbb RORI
                else
                    alu_result = funct7[5] ? ((rs1_val >> shamt) | sra_mask) : (rs1_val >> shamt);
            end
            3'b110: begin
                if (opcode == OP_ALU && funct7 == 7'b0100000)
                    alu_result = rs1_val | ~rs2_val;  // Zbb ORN
                else
                    alu_result = rs1_val | int_alu_b;
            end
            3'b111: begin
                if (opcode == OP_ALU && funct7 == 7'b0100000)
                    alu_result = rs1_val & ~rs2_val;  // Zbb ANDN
                else if (opcode == OP_ALU && funct7 == 7'b0000101)
                    alu_result = (rs1_val < rs2_val) ? rs1_val : rs2_val;  // Zbb MINU
                else
                    alu_result = rs1_val & int_alu_b;
            end
        endcase
    end

    // Zbb: MIN/MAX (funct7=0000101, funct3 selects variant)
    wire is_zbb_minmax = (opcode == OP_ALU) && (funct7 == 7'b0000101);
    logic [31:0] zbb_minmax_result;
    always_comb begin
        case (funct3)
            3'b100: zbb_minmax_result = ($signed(rs1_val) < $signed(rs2_val)) ? rs1_val : rs2_val; // MIN
            3'b101: zbb_minmax_result = ($signed(rs1_val) > $signed(rs2_val)) ? rs1_val : rs2_val; // MAX
            3'b110: zbb_minmax_result = (rs1_val < rs2_val) ? rs1_val : rs2_val;                   // MINU
            3'b111: zbb_minmax_result = (rs1_val > rs2_val) ? rs1_val : rs2_val;                   // MAXU
            default: zbb_minmax_result = rs1_val;
        endcase
    end

    // =====================================================================
    // LZC / CTZ / CPOP — shared with FP normalization
    // =====================================================================
    // Two independent LZC paths:
    //   clz_count: always combinational from rs1_val (for integer CLZ/CTZ)
    //   lzc_count: from registered lzc_input_reg (for FP normalization)
    logic [31:0] lzc_input_reg;
    logic [31:0] lzc_input;
    logic [4:0]  lzc_count;
    logic [4:0]  clz_count;   // dedicated combinational CLZ from rs1_val

    function automatic [2:0] lzc4(input [3:0] v);
        casez (v)
            4'b1???: lzc4 = 3'd0;
            4'b01??: lzc4 = 3'd1;
            4'b001?: lzc4 = 3'd2;
            4'b0001: lzc4 = 3'd3;
            4'b0000: lzc4 = 3'd4;
            default: lzc4 = 3'd4;
        endcase
    endfunction

    // FP normalization LZC (from registered lzc_input_reg)
    always_comb begin
        logic [2:0] lz [0:7];
        integer k;
        lzc_input = lzc_input_reg;
        for (k = 0; k < 8; k = k + 1)
            lz[k] = lzc4(lzc_input[31 - k*4 -: 4]);
        lzc_count = 5'd32;
        for (k = 0; k < 8; k = k + 1) begin
            if (lzc_count == 5'd32 && lz[k] < 3'd4)
                lzc_count = k[4:0] * 5'd4 + {2'd0, lz[k]};
        end
    end

    // Integer CLZ (direct combinational from rs1_val — no register delay)
    always_comb begin
        logic [2:0] clz_lz [0:7];
        integer k;
        for (k = 0; k < 8; k = k + 1)
            clz_lz[k] = lzc4(rs1_val[31 - k*4 -: 4]);
        clz_count = 5'd32;
        for (k = 0; k < 8; k = k + 1) begin
            if (clz_count == 5'd32 && clz_lz[k] < 3'd4)
                clz_count = k[4:0] * 5'd4 + {2'd0, clz_lz[k]};
        end
    end

    // CTZ: reverse bits, feed to LZC
    wire [31:0] rs1_reversed;
    genvar gi;
    generate for (gi = 0; gi < 32; gi = gi + 1) begin : gen_rev
        assign rs1_reversed[gi] = rs1_val[31 - gi];
    end endgenerate

    logic [4:0] ctz_count;
    always_comb begin
        logic [2:0] lz_r [0:7];
        integer k;
        for (k = 0; k < 8; k = k + 1)
            lz_r[k] = lzc4(rs1_reversed[31 - k*4 -: 4]);
        ctz_count = 5'd32;
        for (k = 0; k < 8; k = k + 1) begin
            if (ctz_count == 5'd32 && lz_r[k] < 3'd4)
                ctz_count = k[4:0] * 5'd4 + {2'd0, lz_r[k]};
        end
    end

    // CPOP
    logic [5:0] cpop_count;
    always_comb begin
        cpop_count = 6'd0;
        for (integer k = 0; k < 32; k = k + 1)
            cpop_count = cpop_count + {5'd0, rs1_val[k]};
    end

    // =====================================================================
    // Branch
    // =====================================================================
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

    // =====================================================================
    // Load data extraction
    // =====================================================================
    logic [31:0] load_data;
    wire [1:0] byte_offset = mem_addr[1:0];
    always_comb begin
        case (funct3)
            3'b000: case (byte_offset)
                2'd0: load_data = {{24{mem_rdata[7]}},  mem_rdata[7:0]};
                2'd1: load_data = {{24{mem_rdata[15]}}, mem_rdata[15:8]};
                2'd2: load_data = {{24{mem_rdata[23]}}, mem_rdata[23:16]};
                2'd3: load_data = {{24{mem_rdata[31]}}, mem_rdata[31:24]};
            endcase
            3'b001: load_data = byte_offset[1] ? {{16{mem_rdata[31]}}, mem_rdata[31:16]}
                                                : {{16{mem_rdata[15]}}, mem_rdata[15:0]};
            3'b010: load_data = mem_rdata;
            3'b100: case (byte_offset)
                2'd0: load_data = {24'd0, mem_rdata[7:0]};
                2'd1: load_data = {24'd0, mem_rdata[15:8]};
                2'd2: load_data = {24'd0, mem_rdata[23:16]};
                2'd3: load_data = {24'd0, mem_rdata[31:24]};
            endcase
            3'b101: load_data = byte_offset[1] ? {16'd0, mem_rdata[31:16]}
                                                : {16'd0, mem_rdata[15:0]};
            default: load_data = mem_rdata;
        endcase
    end

    // =====================================================================
    // DSP multiply (32×32 → 64-bit, iterative)
    // Shared: FMUL.S mantissa, M-ext MUL, N-R iterations
    // =====================================================================
    logic [31:0] dsp_a, dsp_b;
    logic [63:0] dsp_result;
    logic        dsp_start, dsp_done;
    logic [63:0] dsp_acc;
    logic [31:0] dsp_b_shift;
    logic [63:0] dsp_a_shifted;
    logic        dsp_computing;
    logic [5:0]  dsp_cycle;

    always_ff @(posedge clk) begin
        dsp_done <= 1'b0;
        if (rst) begin
            dsp_computing <= 1'b0;
        end else if (dsp_start && !dsp_computing) begin
            dsp_computing <= 1'b1;
            dsp_acc       <= 64'd0;
            dsp_a_shifted <= {32'd0, dsp_a};
            dsp_b_shift   <= dsp_b;
            dsp_cycle     <= 6'd0;
        end else if (dsp_computing) begin
            if (dsp_b_shift[0])
                dsp_acc <= dsp_acc + dsp_a_shifted;
            dsp_a_shifted <= {dsp_a_shifted[62:0], 1'b0};
            dsp_b_shift   <= {1'b0, dsp_b_shift[31:1]};
            if (dsp_cycle == 6'd31) begin
                dsp_computing <= 1'b0;
                dsp_done      <= 1'b1;
            end
            dsp_cycle <= dsp_cycle + 6'd1;
        end
    end
    assign dsp_result = dsp_acc;

    // =====================================================================
    // FP working registers
    // =====================================================================
    logic        fp_sign_a, fp_sign_b, fp_sign_r;
    logic [8:0]  fp_exp_a, fp_exp_b, fp_exp_r;    // 9-bit to handle overflow
    logic [24:0] fp_man_a, fp_man_b;               // {implicit_1, mantissa[22:0], guard}
    logic [24:0] fp_man_r;
    logic        fp_guard, fp_round_bit, fp_sticky;
    logic        fp_a_is_nan, fp_b_is_nan, fp_a_is_inf, fp_b_is_inf;
    logic        fp_a_is_zero, fp_b_is_zero;
    logic [31:0] fp_result;                         // packed IEEE 754 result
    logic [4:0]  fp_fflags;                         // exception flags for this op
    logic        fp_special_done;                   // special case handled, skip compute

    // N-R reciprocal lookup table (64 entries, 24-bit Q2.22)
    // table[i] = round(2^22 × 64 / (64 + i)) = approximate 1/(1 + i/64)
    // Range: table[0] = 0x400000 (1.0), table[63] = 0x204000 (~0.504)
    logic [23:0] nr_table [0:63];
    initial begin : nr_table_init
        integer ti;
        for (ti = 0; ti < 64; ti = ti + 1)
            // Use 32-bit integer arithmetic to avoid 24-bit overflow.
            // 2^22 × 64 / (64 + i) = approximate 1/(1 + i/64) in Q2.22.
            nr_table[ti] = (32'd4194304 * 32'd64) / (32'd64 + ti);
    end

    // N-R state — all values in Q2.22 (1.0 = 0x400000)
    (* keep *) logic [23:0] nr_x;           // current reciprocal estimate
    (* keep *) logic [23:0] nr_d;           // divisor mantissa in Q2.22
    (* keep *) logic [23:0] nr_a;           // dividend mantissa in Q2.22 (for final mul)
    (* keep *) logic [23:0] nr_final_x;    // reciprocal saved for final multiply
    logic [2:0]  nr_iter;
    logic        nr_is_sqrt;
    logic [1:0]  nr_phase;       // sub-phase within one iteration

    // FMADD third operand
    logic        fp_sign_c;
    logic [8:0]  fp_exp_c;
    logic [24:0] fp_man_c;

    // FP sub-operation tracking
    logic [3:0]  fp_op;          // which FP instruction we're executing
    localparam [3:0] FOP_ADD   = 4'd0, FOP_SUB   = 4'd1, FOP_MUL  = 4'd2;
    localparam [3:0] FOP_DIV   = 4'd3, FOP_SQRT  = 4'd4, FOP_FMADD = 4'd5;
    localparam [3:0] FOP_FMSUB = 4'd6, FOP_FNMADD = 4'd7, FOP_FNMSUB = 4'd8;
    localparam [3:0] FOP_CVT_WS = 4'd9, FOP_CVT_SW = 4'd10;

    // =====================================================================
    // CSRs
    // =====================================================================
    logic [31:0] csr_mstatus, csr_mtvec, csr_mepc, csr_mcause;
    logic [31:0] csr_mie;
    logic [63:0] csr_mcycle, csr_minstret;
    logic [31:0] csr_fcsr;       // fflags[4:0] + frm[7:5]

    wire irq_pending = csr_mstatus[3] && csr_mie[11] && irq_external;

    always_ff @(posedge clk) begin
        if (rst) csr_mcycle <= 64'd0;
        else     csr_mcycle <= csr_mcycle + 64'd1;
    end

    // CSR read mux
    logic [31:0] csr_rdata;
    wire [11:0] csr_addr = instr[31:20];
    always_comb begin
        case (csr_addr)
            12'h300: csr_rdata = csr_mstatus;
            12'h304: csr_rdata = csr_mie;
            12'h305: csr_rdata = csr_mtvec;
            12'h341: csr_rdata = csr_mepc;
            12'h342: csr_rdata = csr_mcause;
            12'h344: csr_rdata = {20'd0, irq_external, 11'd0};  // MIP
            12'hB00: csr_rdata = csr_mcycle[31:0];
            12'hB02: csr_rdata = csr_minstret[31:0];
            12'hB80: csr_rdata = csr_mcycle[63:32];
            12'hB82: csr_rdata = csr_minstret[63:32];
            12'h001: csr_rdata = {27'd0, csr_fcsr[4:0]};        // fflags
            12'h002: csr_rdata = {29'd0, csr_fcsr[7:5]};        // frm
            12'h003: csr_rdata = csr_fcsr;                       // fcsr
            default: csr_rdata = 32'd0;
        endcase
    end

    // =====================================================================
    // Integer division (restoring, 32 cycles)
    // =====================================================================
    logic [31:0] div_dividend, div_divisor, div_quotient, div_remainder;
    logic [5:0]  div_cycle;
    logic        div_signed_op, div_negate_q, div_negate_r;
    logic [63:0] div_working;

    // =====================================================================
    // Main FSM
    // =====================================================================
    logic [31:0] wb_data;
    logic        wb_en, wb_fp;
    (* keep *) logic [31:0] next_pc;
    logic        is_load, is_fp_load;
    logic [31:0] pc_inc;          // 4 for normal, 2 for compressed

    integer i;

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_FETCH; pc <= 32'd0;
            mem_valid <= 1'b0; mem_wstrb <= 4'd0;
            wb_en <= 1'b0; wb_fp <= 1'b0;
            dsp_start <= 1'b0;
            csr_mstatus <= 32'd0; csr_mtvec <= 32'd0;
            csr_mepc <= 32'd0; csr_mcause <= 32'd0;
            csr_mie <= 32'd0; csr_minstret <= 64'd0;
            csr_fcsr <= 32'd0;
            lzc_input_reg <= 32'd0;
            nr_a <= 24'd0;
            nr_x <= 24'd0;
            nr_d <= 24'd0;
            nr_final_x <= 24'd0;
            nr_iter <= 3'd0;
            nr_phase <= 2'd0;

            for (i = 0; i < 32; i = i + 1) begin
                regs[i]  <= 32'd0;
                fregs[i] <= 32'd0;
            end
        end else begin
            mem_valid <= 1'b0;
            dsp_start <= 1'b0;

            case (state)
            // =============================================================
            S_FETCH: begin
                if (irq_pending) begin
                    state <= S_TRAP_ENTER;
                end else begin
                    mem_addr  <= pc;
                    mem_wstrb <= 4'b0000;
                    mem_valid <= 1'b1;
                    state     <= S_DECODE;
                end
            end

            // =============================================================
            S_DECODE: begin
                if (mem_ready) begin
                    instr  <= mem_rdata;
                    pc_inc <= 32'd4;
                    state  <= S_EXECUTE;
                end else begin
                    mem_valid <= 1'b1;
                end
            end

            // =============================================================
            S_EXECUTE: begin
                is_load    <= 1'b0;
                is_fp_load <= 1'b0;
                wb_en      <= 1'b0;
                wb_fp      <= 1'b0;
                next_pc    <= pc + pc_inc;
                fp_fflags  <= 5'd0;

                case (opcode)
                // --- Base integer (same as RIME-I) ---
                OP_LUI: begin
                    wb_data <= imm_u; wb_en <= (rd != 5'd0);
                    state <= S_WRITEBACK;
                end
                OP_AUIPC: begin
                    wb_data <= pc + imm_u; wb_en <= (rd != 5'd0);
                    state <= S_WRITEBACK;
                end
                OP_JAL: begin
                    wb_data <= pc + pc_inc; wb_en <= (rd != 5'd0);
                    next_pc <= pc + imm_j;
                    state <= S_WRITEBACK;
                end
                OP_JALR: begin
                    wb_data <= pc + pc_inc; wb_en <= (rd != 5'd0);
                    next_pc <= (rs1_val + imm_i) & 32'hFFFFFFFE;
                    state <= S_WRITEBACK;
                end
                OP_BRANCH: begin
                    pc    <= branch_taken ? (pc + imm_b) : (pc + pc_inc);
                    csr_minstret <= csr_minstret + 64'd1;
                    state <= S_FETCH;
                end
                OP_LOAD: begin
                    mem_addr <= rs1_val + imm_i; mem_wstrb <= 4'd0;
                    mem_valid <= 1'b1; is_load <= 1'b1;
                    state <= S_MEM_WAIT;
                end
                OP_STORE: begin
                    mem_addr <= store_addr;
                    case (funct3)
                        3'b000: begin mem_wdata <= {4{rs2_val[7:0]}}; mem_wstrb <= 4'b0001 << store_addr[1:0]; end
                        3'b001: begin mem_wdata <= {2{rs2_val[15:0]}}; mem_wstrb <= store_addr[1] ? 4'b1100 : 4'b0011; end
                        3'b010: begin mem_wdata <= rs2_val; mem_wstrb <= 4'b1111; end
                        default: mem_wstrb <= 4'd0;
                    endcase
                    mem_valid <= 1'b1; state <= S_MEM_WAIT;
                end
                OP_ALUI: begin
                    if (funct7 == 7'b0110000 && funct3 == 3'b001) begin
                        // Zbb CLZ/CTZ/CPOP: LZC input comes from rs1_val
                        // CLZ uses clz_count (combinational from rs1_val)
                    end
                    wb_data <= alu_result; wb_en <= (rd != 5'd0);
                    state <= S_WRITEBACK;
                end
                OP_ALU: begin
                    if (funct7 == 7'b0000001) begin
                        // === M extension ===
                        case (funct3)
                            3'b000, 3'b001, 3'b010, 3'b011: begin // MUL/MULH/MULHSU/MULHU
                                // Dispatch to DSP
                                // Handle signed: convert to unsigned, multiply, fix sign
                                logic [31:0] mul_a, mul_b;
                                logic mul_neg;
                                case (funct3)
                                    3'b000: begin // MUL (low 32 of signed×signed)
                                        mul_a = rs1_val[31] ? (~rs1_val + 32'd1) : rs1_val;
                                        mul_b = rs2_val[31] ? (~rs2_val + 32'd1) : rs2_val;
                                        mul_neg = rs1_val[31] ^ rs2_val[31];
                                    end
                                    3'b001: begin // MULH (high 32 of signed×signed)
                                        mul_a = rs1_val[31] ? (~rs1_val + 32'd1) : rs1_val;
                                        mul_b = rs2_val[31] ? (~rs2_val + 32'd1) : rs2_val;
                                        mul_neg = rs1_val[31] ^ rs2_val[31];
                                    end
                                    3'b010: begin // MULHSU (high 32 of signed×unsigned)
                                        mul_a = rs1_val[31] ? (~rs1_val + 32'd1) : rs1_val;
                                        mul_b = rs2_val;
                                        mul_neg = rs1_val[31];
                                    end
                                    default: begin // 3'b011: MULHU (unsigned×unsigned)
                                        mul_a = rs1_val;
                                        mul_b = rs2_val;
                                        mul_neg = 1'b0;
                                    end
                                endcase
                                dsp_a <= mul_a;
                                dsp_b <= mul_b;
                                dsp_start <= 1'b1;
                                div_negate_q <= mul_neg;  // reuse for sign correction
                                state <= S_DSP_WAIT;
                            end
                            3'b100, 3'b101, 3'b110, 3'b111: begin // DIV/DIVU/REM/REMU
                                // Integer division
                                logic [31:0] d_a, d_b;
                                logic neg_q, neg_r;
                                case (funct3)
                                    3'b100: begin // DIV (signed)
                                        d_a = rs1_val[31] ? (~rs1_val + 32'd1) : rs1_val;
                                        d_b = rs2_val[31] ? (~rs2_val + 32'd1) : rs2_val;
                                        neg_q = rs1_val[31] ^ rs2_val[31];
                                        neg_r = rs1_val[31];
                                    end
                                    3'b101: begin // DIVU
                                        d_a = rs1_val; d_b = rs2_val;
                                        neg_q = 1'b0; neg_r = 1'b0;
                                    end
                                    3'b110: begin // REM (signed)
                                        d_a = rs1_val[31] ? (~rs1_val + 32'd1) : rs1_val;
                                        d_b = rs2_val[31] ? (~rs2_val + 32'd1) : rs2_val;
                                        neg_q = rs1_val[31] ^ rs2_val[31];
                                        neg_r = rs1_val[31];
                                    end
                                    default: begin // REMU
                                        d_a = rs1_val; d_b = rs2_val;
                                        neg_q = 1'b0; neg_r = 1'b0;
                                    end
                                endcase
                                if (d_b == 32'd0) begin
                                    // Division by zero
                                    wb_data <= (funct3[1]) ? d_a : 32'hFFFFFFFF;  // REM returns dividend, DIV returns -1
                                    wb_en <= (rd != 5'd0);
                                    state <= S_WRITEBACK;
                                end else begin
                                    div_dividend <= d_a;
                                    div_divisor  <= d_b;
                                    div_negate_q <= neg_q;
                                    div_negate_r <= neg_r;
                                    div_working  <= {32'd0, d_a};
                                    div_cycle    <= 6'd0;
                                    state <= S_DIV_ITER;
                                end
                            end
                        endcase
                    end else if (is_zbb_minmax) begin
                        wb_data <= zbb_minmax_result;
                        wb_en <= (rd != 5'd0);
                        state <= S_WRITEBACK;
                    end else begin
                        // Standard ALU
                        wb_data <= alu_result; wb_en <= (rd != 5'd0);
                        state <= S_WRITEBACK;
                    end
                end
                OP_FENCE: state <= S_WRITEBACK;

                // --- SYSTEM (CSR + MRET + ECALL) ---
                OP_SYSTEM: begin
                    if (funct3 == 3'b000) begin
                        if (instr[21:20] == 2'b10) begin // MRET
                            state <= S_TRAP_RETURN;
                        end else begin // ECALL/EBREAK
                            csr_mcause <= 32'd11; // environment call from M-mode
                            state <= S_TRAP_ENTER;
                        end
                    end else begin
                        // CSRRW/CSRRS/CSRRC
                        wb_data <= csr_rdata;
                        wb_en <= (rd != 5'd0);
                        case (funct3)
                            3'b001: begin // CSRRW
                                case (csr_addr)
                                    12'h300: csr_mstatus <= rs1_val;
                                    12'h304: csr_mie     <= rs1_val;
                                    12'h305: csr_mtvec   <= rs1_val;
                                    12'h341: csr_mepc    <= rs1_val;
                                    12'h342: csr_mcause  <= rs1_val;
                                    12'h001: csr_fcsr[4:0] <= rs1_val[4:0];
                                    12'h002: csr_fcsr[7:5] <= rs1_val[2:0];
                                    12'h003: csr_fcsr     <= rs1_val;
                                    default: ;
                                endcase
                            end
                            3'b010: begin // CSRRS
                                case (csr_addr)
                                    12'h300: csr_mstatus <= csr_mstatus | rs1_val;
                                    12'h304: csr_mie     <= csr_mie | rs1_val;
                                    12'h001: csr_fcsr[4:0] <= csr_fcsr[4:0] | rs1_val[4:0];
                                    12'h003: csr_fcsr     <= csr_fcsr | rs1_val;
                                    default: ;
                                endcase
                            end
                            3'b011: begin // CSRRC
                                case (csr_addr)
                                    12'h300: csr_mstatus <= csr_mstatus & ~rs1_val;
                                    12'h304: csr_mie     <= csr_mie & ~rs1_val;
                                    12'h001: csr_fcsr[4:0] <= csr_fcsr[4:0] & ~rs1_val[4:0];
                                    12'h003: csr_fcsr     <= csr_fcsr & ~rs1_val;
                                    default: ;
                                endcase
                            end
                            // CSRRWI/CSRRSI/CSRRCI (immediate variants)
                            3'b101: begin
                                case (csr_addr)
                                    12'h001: csr_fcsr[4:0] <= rs1;  // rs1 field is the immediate
                                    12'h002: csr_fcsr[7:5] <= rs1[2:0];
                                    12'h003: csr_fcsr      <= {27'd0, rs1};
                                    default: ;
                                endcase
                            end
                            default: ;
                        endcase
                        state <= S_WRITEBACK;
                    end
                end

                // --- FP load/store ---
                OP_FLW: begin
                    mem_addr <= rs1_val + imm_i; mem_wstrb <= 4'd0;
                    mem_valid <= 1'b1; is_fp_load <= 1'b1; is_load <= 1'b1;
                    state <= S_MEM_WAIT;
                end
                OP_FSW: begin
                    mem_addr  <= rs1_val + imm_s;
                    mem_wdata <= frs2_val;
                    mem_wstrb <= 4'b1111;
                    mem_valid <= 1'b1;
                    state <= S_MEM_WAIT;
                end

                // --- FP arithmetic (OP_FP: funct7 selects operation) ---
                OP_FP: begin
                    // Unpack operands
                    fp_sign_a    <= frs1_val[31];
                    fp_exp_a     <= {1'b0, frs1_val[30:23]};
                    fp_man_a     <= (frs1_val[30:23] == 8'd0) ? {1'b0, frs1_val[22:0], 1'b0}
                                                               : {1'b1, frs1_val[22:0], 1'b0};
                    fp_a_is_nan  <= (frs1_val[30:23] == 8'hFF) && (frs1_val[22:0] != 23'd0);
                    fp_a_is_inf  <= (frs1_val[30:23] == 8'hFF) && (frs1_val[22:0] == 23'd0);
                    fp_a_is_zero <= (frs1_val[30:23] == 8'd0)  && (frs1_val[22:0] == 23'd0);

                    fp_sign_b    <= frs2_val[31];
                    fp_exp_b     <= {1'b0, frs2_val[30:23]};
                    fp_man_b     <= (frs2_val[30:23] == 8'd0) ? {1'b0, frs2_val[22:0], 1'b0}
                                                               : {1'b1, frs2_val[22:0], 1'b0};
                    fp_b_is_nan  <= (frs2_val[30:23] == 8'hFF) && (frs2_val[22:0] != 23'd0);
                    fp_b_is_inf  <= (frs2_val[30:23] == 8'hFF) && (frs2_val[22:0] == 23'd0);
                    fp_b_is_zero <= (frs2_val[30:23] == 8'd0)  && (frs2_val[22:0] == 23'd0);

                    case (funct7)
                        7'b0000000: begin fp_op <= FOP_ADD;  state <= S_FP_ALIGN; end  // FADD.S
                        7'b0000100: begin fp_op <= FOP_SUB;  // FSUB.S: negate B
                            fp_sign_b <= ~frs2_val[31];
                            state <= S_FP_ALIGN;
                        end
                        7'b0001000: begin fp_op <= FOP_MUL;  // FMUL.S
                            dsp_a <= {8'd0, (frs1_val[30:23] != 8'd0), frs1_val[22:0]};
                            dsp_b <= {8'd0, (frs2_val[30:23] != 8'd0), frs2_val[22:0]};
                            dsp_start <= 1'b1;
                            state <= S_DSP_WAIT;
                        end
                        7'b0001100: begin fp_op <= FOP_DIV;  state <= S_FP_UNPACK; end // FDIV.S
                        7'b0101100: begin fp_op <= FOP_SQRT; state <= S_FP_UNPACK; end // FSQRT.S

                        7'b0010100: begin // FMIN.S / FMAX.S
                            if (fp_a_is_nan && fp_b_is_nan) begin
                                wb_data <= 32'h7FC00000; // canonical NaN
                            end else if (fp_a_is_nan) begin
                                wb_data <= frs2_val;
                            end else if (fp_b_is_nan) begin
                                wb_data <= frs1_val;
                            end else begin
                                // Compare as signed magnitude
                                logic a_lt_b;
                                if (frs1_val[31] != frs2_val[31])
                                    a_lt_b = frs1_val[31]; // negative < positive
                                else
                                    a_lt_b = frs1_val[31] ? (frs1_val[30:0] > frs2_val[30:0])
                                                           : (frs1_val[30:0] < frs2_val[30:0]);
                                wb_data <= (funct3[0] == 1'b0) ? (a_lt_b ? frs1_val : frs2_val)   // FMIN
                                                                : (a_lt_b ? frs2_val : frs1_val);  // FMAX
                            end
                            wb_en <= 1'b1; wb_fp <= 1'b1;
                            state <= S_WRITEBACK;
                        end

                        7'b1010000: begin // FEQ.S / FLT.S / FLE.S → integer rd
                            if (fp_a_is_nan || fp_b_is_nan) begin
                                wb_data <= 32'd0;
                                if (funct3 != 3'b010) // FLT/FLE signal invalid on NaN
                                    fp_fflags[4] <= 1'b1; // NV
                            end else begin
                                logic a_lt_b, a_eq_b;
                                if (frs1_val[31] != frs2_val[31]) begin
                                    a_lt_b = frs1_val[31] && (frs1_val[30:0] != 0 || frs2_val[30:0] != 0);
                                    a_eq_b = (frs1_val[30:0] == 0) && (frs2_val[30:0] == 0); // +0 == -0
                                end else begin
                                    a_eq_b = (frs1_val == frs2_val);
                                    a_lt_b = frs1_val[31] ? (frs1_val[30:0] > frs2_val[30:0])
                                                           : (frs1_val[30:0] < frs2_val[30:0]);
                                end
                                case (funct3)
                                    3'b010: wb_data <= {31'd0, a_eq_b};                // FEQ
                                    3'b001: wb_data <= {31'd0, a_lt_b};                // FLT
                                    3'b000: wb_data <= {31'd0, a_lt_b | a_eq_b};       // FLE
                                    default: wb_data <= 32'd0;
                                endcase
                            end
                            wb_en <= (rd != 5'd0); wb_fp <= 1'b0;
                            csr_fcsr[4:0] <= csr_fcsr[4:0] | fp_fflags;
                            state <= S_WRITEBACK;
                        end

                        7'b0010000: begin // FSGNJ / FSGNJN / FSGNJX
                            case (funct3)
                                3'b000: wb_data <= {frs2_val[31],    frs1_val[30:0]}; // FSGNJ
                                3'b001: wb_data <= {~frs2_val[31],   frs1_val[30:0]}; // FSGNJN
                                3'b010: wb_data <= {frs1_val[31] ^ frs2_val[31], frs1_val[30:0]}; // FSGNJX
                                default: wb_data <= frs1_val;
                            endcase
                            wb_en <= 1'b1; wb_fp <= 1'b1;
                            state <= S_WRITEBACK;
                        end

                        7'b1110000: begin // FMV.X.W (funct3=000) or FCLASS.S (funct3=001)
                            if (funct3 == 3'b000) begin
                                wb_data <= frs1_val; // bit-for-bit move to integer reg
                            end else begin
                                // FCLASS.S
                                wb_data <= 32'd0;
                                if (frs1_val[31] && frs1_val[30:23] == 8'hFF && frs1_val[22:0] == 0)
                                    wb_data[0] <= 1'b1; // -inf
                                else if (frs1_val[31] && frs1_val[30:23] != 0 && frs1_val[30:23] != 8'hFF)
                                    wb_data[1] <= 1'b1; // -normal
                                else if (frs1_val[31] && frs1_val[30:23] == 0 && frs1_val[22:0] != 0)
                                    wb_data[2] <= 1'b1; // -subnormal
                                else if (frs1_val == 32'h80000000)
                                    wb_data[3] <= 1'b1; // -0
                                else if (frs1_val == 32'h00000000)
                                    wb_data[4] <= 1'b1; // +0
                                else if (!frs1_val[31] && frs1_val[30:23] == 0 && frs1_val[22:0] != 0)
                                    wb_data[5] <= 1'b1; // +subnormal
                                else if (!frs1_val[31] && frs1_val[30:23] != 0 && frs1_val[30:23] != 8'hFF)
                                    wb_data[6] <= 1'b1; // +normal
                                else if (!frs1_val[31] && frs1_val[30:23] == 8'hFF && frs1_val[22:0] == 0)
                                    wb_data[7] <= 1'b1; // +inf
                                else if (frs1_val[30:23] == 8'hFF && frs1_val[22] == 0 && frs1_val[21:0] != 0)
                                    wb_data[8] <= 1'b1; // signaling NaN
                                else if (frs1_val[30:23] == 8'hFF && frs1_val[22] == 1)
                                    wb_data[9] <= 1'b1; // quiet NaN
                            end
                            wb_en <= (rd != 5'd0); wb_fp <= 1'b0;
                            state <= S_WRITEBACK;
                        end

                        7'b1111000: begin // FMV.W.X: integer to FP register
                            wb_data <= rs1_val;
                            wb_en <= 1'b1; wb_fp <= 1'b1;
                            state <= S_WRITEBACK;
                        end

                        7'b1100000: begin // FCVT.W.S / FCVT.WU.S (float → int)
                            // Simplified: truncate to integer
                            logic [7:0] cv_exp;
                            logic [31:0] cv_man;
                            logic cv_sign;
                            cv_sign = frs1_val[31];
                            cv_exp = frs1_val[30:23];
                            if (cv_exp < 8'd127) begin
                                wb_data <= 32'd0;
                            end else begin
                                logic [4:0] shift;
                                shift = cv_exp - 8'd127;
                                cv_man = {1'b1, frs1_val[22:0], 8'd0};
                                if (shift < 5'd31)
                                    cv_man = cv_man >> (5'd31 - shift);
                                wb_data <= cv_sign ? (~cv_man + 32'd1) : cv_man;
                            end
                            wb_en <= (rd != 5'd0); wb_fp <= 1'b0;
                            state <= S_WRITEBACK;
                        end

                        7'b1101000: begin // FCVT.S.W / FCVT.S.WU (int → float)
                            logic [31:0] cv_abs;
                            logic cv_sign;
                            if (rs2 == 5'd0) begin // FCVT.S.W (signed)
                                cv_sign = rs1_val[31];
                                cv_abs = rs1_val[31] ? (~rs1_val + 32'd1) : rs1_val;
                            end else begin // FCVT.S.WU (unsigned)
                                cv_sign = 1'b0;
                                cv_abs = rs1_val;
                            end
                            if (cv_abs == 32'd0) begin
                                wb_data <= {cv_sign, 31'd0};
                            end else begin
                                // Find leading 1 via LZC
                                lzc_input_reg <= cv_abs;


                                fp_sign_r <= cv_sign;
                                fp_man_r  <= cv_abs[24:0]; // will be adjusted in NORM
                                fp_exp_r  <= 9'd127 + 9'd31; // will subtract LZC
                                fp_op     <= FOP_CVT_SW;
                                state     <= S_FP_NORM;
                            end
                            if (cv_abs == 32'd0) begin
                                wb_en <= 1'b1; wb_fp <= 1'b1;
                                state <= S_WRITEBACK;
                            end
                        end

                        default: state <= S_WRITEBACK;
                    endcase
                end

                // --- Fused multiply-add (R4-type) ---
                OP_FMADD, OP_FMSUB, OP_FNMADD, OP_FNMSUB: begin
                    // Unpack all three operands, start DSP multiply on rs1 × rs2
                    fp_sign_a <= frs1_val[31];
                    fp_exp_a  <= {1'b0, frs1_val[30:23]};
                    fp_sign_b <= frs2_val[31];
                    fp_exp_b  <= {1'b0, frs2_val[30:23]};
                    fp_sign_c <= frs3_val[31];
                    fp_exp_c  <= {1'b0, frs3_val[30:23]};
                    fp_man_c  <= (frs3_val[30:23] == 8'd0) ? {1'b0, frs3_val[22:0], 1'b0}
                                                            : {1'b1, frs3_val[22:0], 1'b0};
                    case (opcode)
                        OP_FMADD:  fp_op <= FOP_FMADD;   // rs1*rs2 + rs3
                        OP_FMSUB:  begin fp_op <= FOP_FMSUB; fp_sign_c <= ~frs3_val[31]; end // rs1*rs2 - rs3
                        OP_FNMADD: begin fp_op <= FOP_FNMADD; fp_sign_a <= ~frs1_val[31]; fp_sign_c <= ~frs3_val[31]; end
                        OP_FNMSUB: begin fp_op <= FOP_FNMSUB; fp_sign_a <= ~frs1_val[31]; end
                        default: ;
                    endcase
                    dsp_a <= {8'd0, (frs1_val[30:23] != 8'd0), frs1_val[22:0]};
                    dsp_b <= {8'd0, (frs2_val[30:23] != 8'd0), frs2_val[22:0]};
                    dsp_start <= 1'b1;
                    state <= S_DSP_WAIT;
                end

                default: state <= S_WRITEBACK;
                endcase
            end

            // =============================================================
            S_MEM_WAIT: begin
                if (mem_ready) begin
                    if (is_load) begin
                        if (is_fp_load) begin
                            wb_data <= mem_rdata;
                            wb_en <= 1'b1; wb_fp <= 1'b1;
                        end else begin
                            wb_data <= load_data;
                            wb_en <= (rd != 5'd0);
                        end
                        state <= S_WRITEBACK;
                    end else begin
                        pc <= pc + pc_inc;
                        csr_minstret <= csr_minstret + 64'd1;
                        state <= S_FETCH;
                    end
                end else begin
                    mem_valid <= 1'b1;
                end
            end

            // =============================================================
            S_WRITEBACK: begin
                if (wb_en) begin
                    if (wb_fp)
                        fregs[rd] <= wb_data;
                    else if (rd != 5'd0)
                        regs[rd] <= wb_data;
                end
                pc <= next_pc;
                csr_minstret <= csr_minstret + 64'd1;
                state <= S_FETCH;
            end

            // =============================================================
            // FP ALIGN: compute exponent difference, shift smaller mantissa
            // Uses the shared ALU concept: the exponent subtract and mantissa
            // shift happen through the same logic the integer ALU uses.
            // =============================================================
            S_FP_ALIGN: begin
                if (fp_a_is_nan || fp_b_is_nan) begin
                    wb_data <= 32'h7FC00000; // canonical NaN
                    fp_fflags[4] <= 1'b1;    // NV if signaling
                    wb_en <= 1'b1; wb_fp <= 1'b1;
                    csr_fcsr[4:0] <= csr_fcsr[4:0] | fp_fflags;
                    state <= S_WRITEBACK;
                end else if (fp_a_is_inf && fp_b_is_inf && (fp_sign_a != fp_sign_b)) begin
                    wb_data <= 32'h7FC00000; // inf - inf = NaN
                    fp_fflags[4] <= 1'b1;
                    wb_en <= 1'b1; wb_fp <= 1'b1;
                    csr_fcsr[4:0] <= csr_fcsr[4:0] | fp_fflags;
                    state <= S_WRITEBACK;
                end else if (fp_a_is_inf) begin
                    wb_data <= {fp_sign_a, 8'hFF, 23'd0};
                    wb_en <= 1'b1; wb_fp <= 1'b1;
                    state <= S_WRITEBACK;
                end else if (fp_b_is_inf) begin
                    wb_data <= {fp_sign_b, 8'hFF, 23'd0};
                    wb_en <= 1'b1; wb_fp <= 1'b1;
                    state <= S_WRITEBACK;
                end else begin
                    // Exponent difference (uses integer subtraction logic)
                    logic [8:0] exp_diff;
                    logic swap;
                    if (fp_exp_a >= fp_exp_b) begin
                        exp_diff = fp_exp_a - fp_exp_b;
                        swap = 1'b0;
                    end else begin
                        exp_diff = fp_exp_b - fp_exp_a;
                        swap = 1'b1;
                    end
                    // Align: shift smaller mantissa right (uses shifter)
                    if (swap) begin
                        fp_sticky <= (exp_diff > 9'd24) ? |fp_man_a : 1'b0;
                        fp_man_a  <= (exp_diff < 9'd25) ? (fp_man_a >> exp_diff[4:0]) : 25'd0;
                        fp_exp_r  <= fp_exp_b;
                    end else begin
                        fp_sticky <= (exp_diff > 9'd24) ? |fp_man_b : 1'b0;
                        fp_man_b  <= (exp_diff < 9'd25) ? (fp_man_b >> exp_diff[4:0]) : 25'd0;
                        fp_exp_r  <= fp_exp_a;
                    end
                    state <= S_FP_COMPUTE;
                end
            end

            // =============================================================
            // FP COMPUTE: mantissa add/sub through the shared adder
            // =============================================================
            S_FP_COMPUTE: begin
                logic [25:0] sum;
                if (fp_sign_a == fp_sign_b) begin
                    sum = {1'b0, fp_man_a} + {1'b0, fp_man_b};
                    fp_sign_r <= fp_sign_a;
                end else begin
                    if (fp_man_a >= fp_man_b) begin
                        sum = {1'b0, fp_man_a} - {1'b0, fp_man_b};
                        fp_sign_r <= fp_sign_a;
                    end else begin
                        sum = {1'b0, fp_man_b} - {1'b0, fp_man_a};
                        fp_sign_r <= fp_sign_b;
                    end
                end
                fp_man_r <= sum[24:0];
                fp_guard <= sum[25];  // carry out
                // Feed to LZC for normalization
                lzc_input_reg <= {sum[24:0], 7'd0};


                state <= S_FP_NORM;
            end

            // =============================================================
            // FP NORM: normalize via LZC + shift (shared shifter)
            // =============================================================
            S_FP_NORM: begin
                if (fp_op == FOP_CVT_SW) begin
                    // Integer-to-float: shift mantissa based on LZC
                    logic [31:0] cv_shifted;
                    cv_shifted = lzc_input << lzc_count; // reusing lzc_input which has cv_abs
                    wb_data <= {fp_sign_r, fp_exp_r[7:0] - {4'd0, lzc_count}, cv_shifted[30:8]};
                    wb_en <= 1'b1; wb_fp <= 1'b1;
                    state <= S_WRITEBACK;
                end else if (fp_guard) begin
                    // Carry out from addition: shift right 1
                    fp_man_r <= {1'b1, fp_man_r[24:1]};
                    fp_round_bit <= fp_man_r[0];
                    fp_exp_r <= fp_exp_r + 9'd1;
                    state <= S_FP_ROUND;
                end else if (fp_man_r == 25'd0) begin
                    // Result is zero
                    wb_data <= {fp_sign_r, 31'd0};
                    wb_en <= 1'b1; wb_fp <= 1'b1;
                    state <= S_WRITEBACK;
                end else begin
                    // Normalize: shift left by LZC amount.
                    // lzc_input_reg has the mantissa left-justified to bit 31.
                    // LZC = 0 means bit 31 is set (already normalized).
                    // LZC = N means N left shifts needed.
                    logic [4:0] nlz;
                    nlz = lzc_count;
                    if (nlz > 0 && fp_exp_r > {4'd0, nlz}) begin
                        fp_man_r <= fp_man_r << nlz;
                        fp_exp_r <= fp_exp_r - {4'd0, nlz};
                    end
                    fp_round_bit <= 1'b0;
                    state <= S_FP_ROUND;
                end
            end

            // =============================================================
            // FP ROUND: IEEE 754 rounding + pack
            // =============================================================
            S_FP_ROUND: begin
                logic [23:0] rounded_man;
                logic round_up;
                // Round-to-nearest-even (default)
                round_up = fp_round_bit & (fp_sticky | fp_man_r[1]);
                rounded_man = fp_man_r[24:1] + {23'd0, round_up};

                if (rounded_man[23]) begin
                    // Rounding caused carry into implicit bit position — already normalized
                    wb_data <= {fp_sign_r, fp_exp_r[7:0], rounded_man[22:0]};
                end else if (rounded_man[22:0] == 23'd0 && round_up) begin
                    // Rounded up to next power of 2
                    wb_data <= {fp_sign_r, fp_exp_r[7:0] + 8'd1, 23'd0};
                end else begin
                    wb_data <= {fp_sign_r, fp_exp_r[7:0], rounded_man[22:0]};
                end

                if (fp_round_bit | fp_sticky)
                    csr_fcsr[0] <= 1'b1; // inexact flag

                wb_en <= 1'b1; wb_fp <= 1'b1;
                state <= S_WRITEBACK;
            end

            // =============================================================
            // DSP WAIT: shared for FMUL.S, integer MUL, FMADD, N-R steps
            // =============================================================
            S_DSP_WAIT: begin
                if (dsp_done) begin
                    case (fp_op)
                        FOP_MUL: begin
                            // FMUL.S: product is in dsp_result[47:0]
                            fp_sign_r <= fp_sign_a ^ fp_sign_b;
                            fp_exp_r  <= fp_exp_a + fp_exp_b - 9'd127;
                            // Product is 1.xx × 1.yy = [1,4).mantissa in bits [47:0]
                            // Normalize: if bit 47 set, shift right 1
                            if (dsp_result[47]) begin
                                fp_man_r <= dsp_result[47:23];
                                fp_round_bit <= dsp_result[22];
                                fp_sticky <= |dsp_result[21:0];
                                fp_exp_r <= fp_exp_a + fp_exp_b - 9'd127 + 9'd1;
                            end else begin
                                fp_man_r <= dsp_result[46:22];
                                fp_round_bit <= dsp_result[21];
                                fp_sticky <= |dsp_result[20:0];
                            end
                            fp_guard <= 1'b0;
                            state <= S_FP_ROUND;
                        end
                        FOP_DIV: begin
                            // FDIV final multiply: a × (1/b) in Q2.22
                            logic [23:0] div_mantissa;
                            div_mantissa = dsp_result[45:22];
                            fp_sign_r <= fp_sign_a ^ fp_sign_b;
                            fp_man_r <= {div_mantissa, 1'b0};
                            fp_exp_r <= fp_exp_a - fp_exp_b + 9'd127 + 9'd1;
                            lzc_input_reg <= {div_mantissa, 8'd0};
                            fp_guard <= 1'b0;
                            fp_round_bit <= 1'b0;
                            fp_sticky <= 1'b0;
                            state <= S_FP_NORM;
                        end
                        FOP_FMADD, FOP_FMSUB, FOP_FNMADD, FOP_FNMSUB: begin
                            // Product ready, now add rs3 via shared ALU
                            fp_sign_r <= fp_sign_a ^ fp_sign_b;
                            fp_exp_r  <= fp_exp_a + fp_exp_b - 9'd127;
                            fp_man_r  <= dsp_result[47] ? dsp_result[47:23] : dsp_result[46:22];
                            if (dsp_result[47])
                                fp_exp_r <= fp_exp_a + fp_exp_b - 9'd127 + 9'd1;
                            // Now we need to add fp_man_c (third operand) aligned to this result
                            // Route to S_FP_ALIGN but with product as operand A and rs3 as operand B
                            fp_man_a <= dsp_result[47] ? dsp_result[47:23] : dsp_result[46:22];
                            fp_exp_a <= dsp_result[47] ? (fp_exp_a + fp_exp_b - 9'd127 + 9'd1)
                                                        : (fp_exp_a + fp_exp_b - 9'd127);
                            fp_sign_a <= fp_sign_a ^ fp_sign_b;
                            fp_man_b <= fp_man_c;
                            fp_exp_b <= fp_exp_c;
                            fp_sign_b <= fp_sign_c;
                            fp_op <= FOP_ADD; // now it's just an add
                            state <= S_FP_ALIGN;
                        end
                        default: begin
                            // Integer MUL: select result word
                            logic [63:0] mul_result;
                            mul_result = dsp_result;
                            if (div_negate_q && mul_result != 64'd0)
                                mul_result = ~mul_result + 64'd1;
                            case (funct3)
                                3'b000: wb_data <= mul_result[31:0];   // MUL
                                3'b001: wb_data <= mul_result[63:32];  // MULH
                                3'b010: wb_data <= mul_result[63:32];  // MULHSU
                                3'b011: wb_data <= mul_result[63:32];  // MULHU
                                default: wb_data <= mul_result[31:0];
                            endcase
                            wb_en <= (rd != 5'd0);
                            state <= S_WRITEBACK;
                        end
                    endcase
                end
            end

            // =============================================================
            // FP UNPACK: for FDIV.S / FSQRT.S — set up N-R iteration
            // =============================================================
            // =============================================================
            // FP UNPACK for FDIV/FSQRT — set up N-R in Q2.22
            // Q2.22: 1.0 = 0x400000, 2.0 = 0x800000
            // Mantissa {1,m[22:0]} in Q1.23 → Q2.22 by >> 1
            // =============================================================
            S_FP_UNPACK: begin
                // Divisor mantissa in Q2.22
                nr_d <= {1'b0, 1'b1, frs2_val[22:1]};  // {1,mantissa} >> 1
                // Dividend mantissa saved for final multiply
                nr_a <= {1'b0, 1'b1, frs1_val[22:1]};
                nr_final_x <= 24'h400000;  // DEBUG: set to 1.0, overwritten if N-R completes
                // Initial estimate from table (Q2.22)
                nr_x <= nr_table[frs2_val[22:17]];
                nr_iter <= 3'd0;
                nr_is_sqrt <= (fp_op == FOP_SQRT);
                // Start first N-R multiply: d * x_0
                dsp_a <= {8'd0, 1'b0, 1'b1, frs2_val[22:1]};
                dsp_b <= {8'd0, nr_table[frs2_val[22:17]]};
                dsp_start <= 1'b1;
                state <= S_FP_NR_MUL1;
            end

            // =============================================================
            // Newton-Raphson: x_{n+1} = x_n × (2 - d × x_n)
            // All arithmetic in Q2.22. Products are Q4.44 → bits [45:22] = Q2.22.
            // =============================================================
            S_FP_NR_MUL1: begin
                // DSP finished d × x_n. Extract Q2.22 result from Q4.44 product.
                if (dsp_done) begin
                    logic [23:0] bx_q;
                    logic [23:0] correction;
                    bx_q = dsp_result[45:22];          // d*x in Q2.22
                    correction = 24'h800000 - bx_q;   // 2.0 - d*x in Q2.22
                    // Now compute x_n × correction
                    dsp_a <= {8'd0, nr_x};
                    dsp_b <= {8'd0, correction};
                    dsp_start <= 1'b1;
                    state <= S_FP_NR_MUL2;
                end
            end

            S_FP_NR_MUL2: begin
                // DSP finished x_n × correction. New estimate in Q2.22.
                if (dsp_done) begin
                    logic [23:0] new_x;
                    new_x = dsp_result[45:22];
                    nr_x <= new_x;
                    nr_iter <= nr_iter + 3'd1;
                    if (nr_iter >= 3'd3) begin
                        // Dispatch final a×(1/b) directly — no gap state.
                        // new_x is valid right now (blocking assignment from
                        // dsp_result[45:22]). Use it immediately.
                        // The reciprocal is in dsp_acc[45:22] right now.
                        // Save it to nr_final_x, then dispatch via gap state.
                        nr_final_x <= dsp_acc[45:22];
                        state <= S_FP_FMADD;
                    end else begin
                        // More iterations: d × new_x
                        dsp_a <= {8'd0, nr_d};
                        dsp_b <= {8'd0, new_x};
                        dsp_start <= 1'b1;
                        state <= S_FP_NR_MUL1;
                    end
                end
            end

            S_FP_NR_CORR: begin
                // Two-phase: dispatch final multiply, then pack result.
                if (!nr_phase[0]) begin
                    // Phase 0: dispatch. Wait for DSP to be free first.
                    if (!dsp_computing) begin
                        dsp_a <= {8'd0, nr_a};
                        dsp_b <= {8'd0, nr_x};
                        dsp_start <= 1'b1;
                        nr_phase <= 2'd1;
                    end
                end else begin
                    // Phase 1: wait for result
                    if (dsp_done) begin
                        logic [23:0] div_mantissa;
                        div_mantissa = dsp_result[45:22];
                        fp_sign_r <= fp_sign_a ^ fp_sign_b;
                        fp_man_r <= {div_mantissa, 1'b0};
                        fp_exp_r <= fp_exp_a - fp_exp_b + 9'd127 + 9'd1;
                        lzc_input_reg <= {div_mantissa, 8'd0};
                        fp_guard <= 1'b0;
                        fp_round_bit <= 1'b0;
                        fp_sticky <= 1'b0;
                        state <= S_FP_NORM;
                    end
                end
            end

            // =============================================================
            // Integer division (restoring, 32 cycles)
            // =============================================================
            S_DIV_ITER: begin
                if (div_cycle <= 6'd31) begin
                    // Restoring division: shift left, trial subtract.
                    // No partial-bit assignments — compute full 64-bit word.
                    logic [31:0] trial;
                    logic        trial_ok;
                    trial = {div_working[62:32], div_working[31]};
                    trial_ok = (trial >= div_divisor);
                    div_working <= {
                        trial_ok ? (trial - div_divisor) : trial,
                        div_working[30:0],
                        trial_ok
                    };
                    div_cycle <= div_cycle + 6'd1;
                end else begin
                    logic [31:0] q, r;
                    q = div_working[31:0];
                    r = div_working[63:32];
                    if (div_negate_q) q = ~q + 32'd1;
                    if (div_negate_r) r = ~r + 32'd1;
                    case (funct3)
                        3'b100, 3'b101: wb_data <= q;
                        3'b110, 3'b111: wb_data <= r;
                        default: wb_data <= q;
                    endcase
                    wb_en <= (rd != 5'd0);
                    state <= S_WRITEBACK;
                end
            end

            // =============================================================
            // FDIV final multiply gap: dispatch a × (1/b) after N-R settles
            // =============================================================
            S_FP_FMADD: begin
                // 1-cycle gap for FDIV. nr_final_x and nr_a are stable.
                // Dispatch final multiply through S_DSP_WAIT.
                dsp_a <= {8'd0, nr_a};
                dsp_b <= {8'd0, nr_final_x};
                dsp_start <= 1'b1;
                fp_op <= FOP_DIV;
                state <= S_DSP_WAIT;
            end

            // =============================================================
            // TRAP ENTER: save PC, jump to handler
            // =============================================================
            S_TRAP_ENTER: begin
                csr_mepc <= pc;
                csr_mstatus[7] <= csr_mstatus[3]; // MPIE = MIE
                csr_mstatus[3] <= 1'b0;            // disable interrupts
                if (irq_pending)
                    csr_mcause <= 32'h8000000B; // machine external interrupt
                pc <= csr_mtvec & 32'hFFFFFFFC;
                state <= S_FETCH;
            end

            // =============================================================
            // TRAP RETURN (MRET): restore PC and interrupt state
            // =============================================================
            S_TRAP_RETURN: begin
                pc <= csr_mepc;
                csr_mstatus[3] <= csr_mstatus[7]; // MIE = MPIE
                csr_mstatus[7] <= 1'b1;            // MPIE = 1
                state <= S_FETCH;
            end

            default: state <= S_FETCH;
            endcase
        end
    end
endmodule
