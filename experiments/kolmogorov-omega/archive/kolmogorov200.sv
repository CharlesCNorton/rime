// KOLMOGOROV: 200-interpreter parallel Kolmogorov complexity estimator.
//
// Programs enumerated via a base-6 odometer counter — no division.
// Each batch: 200 interpreters run 200 consecutive programs in parallel.
// The controller checks which produced the target output. The shortest
// program that matches is the K(target) estimate.
//
// Register map: see module ports below.

module kolmogorov200 (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    (* keep *) output logic [31:0] reg_rdata,
    (* keep *) output logic        reg_ready
);

    localparam integer N_INTERP = 25;
    localparam integer PROG_LEN = 6;
    localparam integer BATCH_STEPS = 260;

    // --- Interpreter array ---
    logic        interp_start;
    logic [23:0] interp_prog [0:N_INTERP-1];  // 8 instructions × 3 bits
    logic [7:0]  interp_result [0:N_INTERP-1];
    logic        interp_done [0:N_INTERP-1];
    logic        interp_halted [0:N_INTERP-1];
    logic [7:0]  init_a_reg, init_b_reg;

    genvar gi;
    generate
        for (gi = 0; gi < N_INTERP; gi = gi + 1) begin : gen_interp
            tiny_interp INTERP (
                .clk(clk), .rst(rst),
                .start(interp_start),
                .program(interp_prog[gi]),
                .init_a(init_a_reg),
                .init_b(init_b_reg),
                .result(interp_result[gi]),
                .done(interp_done[gi]),
                .halted(interp_halted[gi])
            );
        end
    endgenerate

    // --- Base-6 odometer: 8 digits, each 0-5 ---
    logic [2:0] odo [0:7];  // 8 base-6 digits

    // Increment a base-6 8-digit number by 1, returns {carry, d7..d0}
    function automatic [24:0] base6_inc(
        input [2:0] d7, d6, d5, d4, d3, d2, d1, d0
    );
        logic [2:0] r [0:7];
        logic c;
        r[0] = d0 + 3'd1; c = (d0 == 3'd5); if (c) r[0] = 3'd0;
        r[1] = c ? d1 + 3'd1 : d1; if (c && d1 == 3'd5) begin r[1] = 3'd0; c = 1; end else c = 0;
        r[2] = c ? d2 + 3'd1 : d2; if (c && d2 == 3'd5) begin r[2] = 3'd0; c = 1; end else c = 0;
        r[3] = c ? d3 + 3'd1 : d3; if (c && d3 == 3'd5) begin r[3] = 3'd0; c = 1; end else c = 0;
        r[4] = c ? d4 + 3'd1 : d4; if (c && d4 == 3'd5) begin r[4] = 3'd0; c = 1; end else c = 0;
        r[5] = c ? d5 + 3'd1 : d5; if (c && d5 == 3'd5) begin r[5] = 3'd0; c = 1; end else c = 0;
        r[6] = c ? d6 + 3'd1 : d6; if (c && d6 == 3'd5) begin r[6] = 3'd0; c = 1; end else c = 0;
        r[7] = c ? d7 + 3'd1 : d7; if (c && d7 == 3'd5) begin r[7] = 3'd0; c = 1; end else c = 0;
        base6_inc = {c, r[7], r[6], r[5], r[4], r[3], r[2], r[1], r[0]};
    endfunction

    // Pack 8 base-6 digits into a 24-bit program
    function automatic [23:0] pack_digits(
        input [2:0] d7, d6, d5, d4, d3, d2, d1, d0
    );
        pack_digits = {d7, d6, d5, d4, d3, d2, d1, d0};
    endfunction

    // --- State ---
    logic [7:0]  target;
    logic [3:0]  search_len;
    logic [23:0] single_prog;

    localparam [2:0] S_IDLE    = 3'd0;
    localparam [2:0] S_LOAD    = 3'd1;
    localparam [2:0] S_RUN     = 3'd2;
    localparam [2:0] S_COLLECT = 3'd3;
    localparam [2:0] S_DONE    = 3'd4;
    localparam [2:0] S_SINGLE  = 3'd5;
    localparam [2:0] S_SINGLEW = 3'd6;

    // (* keep *) prevents yosys from constant-folding signals through the
    // module boundary. Without these, yosys may determine the FSM is
    // unreachable from reset and optimize away the entire module, collapsing
    // bus signals the CPU depends on.
    (* keep *) logic [2:0]  state;
    (* keep *) logic [31:0] progs_tried;
    (* keep *) logic [31:0] batch_num;
    (* keep *) logic [31:0] match_count;
    (* keep *) logic [31:0] halt_count;   // total halting programs (for Omega)
    (* keep *) logic [8:0]  run_timer;
    (* keep *) logic        all_done;
    logic        enumeration_done;  // odometer overflowed

    logic        k_found;
    logic [23:0] k_program;
    logic [7:0]  k_value;
    logic        run_done_flag;
    logic [7:0]  run_output;
    logic        run_halted;

    logic [31:0] total_programs;

    function automatic [31:0] prog_space(input [3:0] len);
        case (len)
            3'd1: prog_space = 32'd6;
            3'd2: prog_space = 32'd36;
            3'd3: prog_space = 32'd216;
            3'd4: prog_space = 32'd1296;
            3'd5: prog_space = 32'd7776;
            3'd6: prog_space = 32'd46656;
            3'd7: prog_space = 32'd279936;
            4'd8: prog_space = 32'd1679616;
            default: prog_space = 32'd1679616;
        endcase
    endfunction

    always_comb begin
        all_done = 1'b1;
        for (int i = 0; i < N_INTERP; i = i + 1)
            if (!interp_done[i]) all_done = 1'b0;
    end

    // --- Main FSM ---
    // LOAD: sequentially compute 200 programs from the odometer by
    //       incrementing it 200 times (one per cycle). Then start all.
    logic [7:0]  load_idx;
    logic [2:0]  cur_d [0:7];  // working copy of odometer during load

    always_ff @(posedge clk) begin
        interp_start <= 1'b0;

        if (rst) begin
            state <= S_IDLE;
            target <= 8'd0;
            search_len <= 4'd8;
            init_a_reg <= 8'd0; init_b_reg <= 8'd0;
            k_found <= 1'b0; k_value <= 8'd0; k_program <= 24'd0;
            run_done_flag <= 1'b0;
            progs_tried <= 32'd0; batch_num <= 32'd0; match_count <= 32'd0; halt_count <= 32'd0;
            enumeration_done <= 1'b0;
            for (int i = 0; i < 8; i = i + 1) odo[i] <= 3'd0;
        end else begin
            case (state)
                S_IDLE: ;

                S_LOAD: begin
                    if (load_idx == 0) begin
                        // Initialize working copy from odometer
                        for (int i = 0; i < 8; i = i + 1) cur_d[i] <= odo[i];
                    end

                    // Assign current program to interpreter[load_idx]
                    interp_prog[load_idx] <= pack_digits(cur_d[7], cur_d[6], cur_d[5], cur_d[4], cur_d[3], cur_d[2], cur_d[1], cur_d[0]);

                    // Increment working counter for next interpreter
                    begin
                        logic [24:0] nxt;
                        nxt = base6_inc(cur_d[7], cur_d[6], cur_d[5], cur_d[4], cur_d[3], cur_d[2], cur_d[1], cur_d[0]);
                        cur_d[0] <= nxt[2:0];
                        cur_d[1] <= nxt[5:3];
                        cur_d[2] <= nxt[8:6];
                        cur_d[3] <= nxt[11:9];
                        cur_d[4] <= nxt[14:12];
                        cur_d[5] <= nxt[17:15];
                        cur_d[6] <= nxt[20:18];
                        cur_d[7] <= nxt[23:21];
                        if (nxt[24]) enumeration_done <= 1'b1;
                    end

                    if (load_idx >= N_INTERP - 1) begin
                        // All loaded — update odometer to cur_d (which is now odo + N_INTERP)
                        for (int i = 0; i < 8; i = i + 1) odo[i] <= cur_d[i];
                        interp_start <= 1'b1;
                        run_timer <= 9'd0;
                        state <= S_RUN;
                    end else begin
                        load_idx <= load_idx + 8'd1;
                    end
                end

                S_RUN: begin
                    run_timer <= run_timer + 9'd1;
                    if (all_done || run_timer >= BATCH_STEPS)
                        state <= S_COLLECT;
                end

                S_COLLECT: begin
                    // Count matches and halts combinationally
                    logic [7:0] batch_matches;
                    logic [7:0] batch_halts;
                    logic       found_first;
                    logic [23:0] first_prog;
                    batch_matches = 8'd0;
                    batch_halts = 8'd0;
                    found_first = 1'b0;
                    first_prog = 24'd0;
                    for (int i = 0; i < N_INTERP; i = i + 1) begin
                        if (interp_halted[i]) begin
                            batch_halts = batch_halts + 8'd1;
                            if (interp_result[i] == target) begin
                                batch_matches = batch_matches + 8'd1;
                                if (!found_first && !k_found) begin
                                    found_first = 1'b1;
                                    first_prog = interp_prog[i];
                                end
                            end
                        end
                    end
                    match_count <= match_count + {24'd0, batch_matches};
                    halt_count <= halt_count + {24'd0, batch_halts};
                    if (found_first) begin
                        k_found <= 1'b1;
                        k_value <= search_len;
                        k_program <= first_prog;
                    end
                    progs_tried <= progs_tried + N_INTERP;
                    batch_num <= batch_num + 32'd1;

                    if (enumeration_done || progs_tried + N_INTERP >= prog_space(search_len))
                        state <= S_DONE;
                    else begin
                        load_idx <= 8'd0;
                        state <= S_LOAD;
                    end
                end

                S_DONE: state <= S_IDLE;

                S_SINGLE: begin
                    interp_prog[0] <= single_prog;
                    interp_start <= 1'b1;
                    run_timer <= 9'd0;
                    state <= S_SINGLEW;
                end

                S_SINGLEW: begin
                    run_timer <= run_timer + 9'd1;
                    if (interp_done[0] || run_timer >= BATCH_STEPS) begin
                        run_output <= interp_result[0];
                        run_halted <= interp_halted[0];
                        run_done_flag <= 1'b1;
                        state <= S_IDLE;
                    end
                end

                default: state <= S_IDLE;
            endcase

            if (reg_wr) begin
                case (reg_addr)
                    12'h000: target <= reg_wdata[7:0];
                    12'h004: begin
                        if (reg_wdata[0]) begin
                            k_found <= 1'b0;
                            progs_tried <= 32'd0; batch_num <= 32'd0; match_count <= 32'd0; halt_count <= 32'd0;
                            enumeration_done <= 1'b0;
                            for (int i = 0; i < 8; i = i + 1) odo[i] <= 3'd0;
                            load_idx <= 8'd0;
                            state <= S_LOAD;
                        end
                        if (reg_wdata[1]) begin
                            run_done_flag <= 1'b0;
                            state <= S_SINGLE;
                        end
                        if (reg_wdata[2]) state <= S_IDLE;
                    end
                    12'h014: single_prog <= reg_wdata[23:0];
                    12'h01C: init_a_reg <= reg_wdata[7:0];
                    12'h020: init_b_reg <= reg_wdata[7:0];
                    12'h02C: search_len <= reg_wdata[3:0];
                    default: ;
                endcase
            end
        end
    end

    // --- Register reads ---
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            reg_rdata <= 32'd0;
        end else if (reg_wr) begin
            reg_ready <= 1'b1;
            reg_rdata <= 32'd0;
        end else if (reg_rd) begin
            reg_ready <= 1'b1;
            case (reg_addr)
                12'h008: reg_rdata <= {28'd0, 1'b0, run_done_flag, k_found, state != S_IDLE};
                12'h00C: reg_rdata <= {24'd0, k_value};
                12'h010: reg_rdata <= {8'd0, k_program};
                12'h018: reg_rdata <= {23'd0, run_halted, run_output};
                12'h024: reg_rdata <= batch_num;
                12'h028: reg_rdata <= progs_tried;
                12'h02C: reg_rdata <= {28'd0, search_len};
                12'h030: reg_rdata <= match_count;
                12'h034: reg_rdata <= halt_count;     // Omega numerator
                default: reg_rdata <= 32'd0;
            endcase
        end
    end

endmodule
