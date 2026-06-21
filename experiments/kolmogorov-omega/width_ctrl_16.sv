module width_ctrl_16 #(parameter integer N_INTERP=16) (
    input wire clk,input wire rst,input wire [11:0] reg_addr,input wire [31:0] reg_wdata,
    input wire reg_wr,input wire reg_rd,(* keep *) output logic [31:0] reg_rdata,(* keep *) output logic reg_ready);
    logic interp_start;logic [23:0] interp_prog[0:N_INTERP-1];
    logic [15:0] interp_result[0:N_INTERP-1];logic interp_done[0:N_INTERP-1];logic interp_halted[0:N_INTERP-1];
    logic [15:0] init_a_reg,init_b_reg;logic [23:0] isa_lut_reg;
    genvar gi;generate for(gi=0;gi<N_INTERP;gi=gi+1) begin:gen_interp
        tiny_interp_w16 I(.clk(clk),.rst(rst),.start(interp_start),
            .program(interp_prog[gi]),.init_a(init_a_reg),.init_b(init_b_reg),
            .isa_lut(isa_lut_reg),.result(interp_result[gi]),.done(interp_done[gi]),.halted(interp_halted[gi]));
    end endgenerate
    logic [2:0] cur_d[0:7];
    function automatic [24:0] base6_inc(input [2:0] d7,d6,d5,d4,d3,d2,d1,d0);
        logic [2:0] r[0:7];logic c;r[0]=d0+1;c=(d0==5);if(c)r[0]=0;
        r[1]=c?d1+1:d1;if(c&&d1==5)begin r[1]=0;c=1;end else c=0;
        r[2]=c?d2+1:d2;if(c&&d2==5)begin r[2]=0;c=1;end else c=0;
        r[3]=c?d3+1:d3;if(c&&d3==5)begin r[3]=0;c=1;end else c=0;
        r[4]=c?d4+1:d4;if(c&&d4==5)begin r[4]=0;c=1;end else c=0;
        r[5]=c?d5+1:d5;if(c&&d5==5)begin r[5]=0;c=1;end else c=0;
        r[6]=c?d6+1:d6;if(c&&d6==5)begin r[6]=0;c=1;end else c=0;
        r[7]=c?d7+1:d7;if(c&&d7==5)begin r[7]=0;c=1;end else c=0;
        base6_inc={c,r[7],r[6],r[5],r[4],r[3],r[2],r[1],r[0]};endfunction
    function automatic [23:0] pack_digits(input [2:0] d7,d6,d5,d4,d3,d2,d1,d0);
        pack_digits={d7,d6,d5,d4,d3,d2,d1,d0};endfunction
    logic [7:0] target;logic [3:0] search_len;
    localparam [2:0] S_IDLE=0,S_LOAD=1,S_RUN=2,S_COLLECT=3,S_DONE=4;
    (* keep *) logic [2:0] state;(* keep *) logic [31:0] progs_tried,halt_count,match_count;
    (* keep *) logic [16:0] run_timer;(* keep *) logic all_done;
    logic enumeration_done;logic [4:0] load_idx,collect_idx;
    always_ff @(posedge clk) begin reg_ready<=0;interp_start<=0;
        if(rst) begin state<=S_IDLE;progs_tried<=0;halt_count<=0;match_count<=0;
            enumeration_done<=0;init_a_reg<=0;init_b_reg<=0;search_len<=8;target<=0;
            isa_lut_reg<=24'h543210;for(int i=0;i<8;i=i+1)cur_d[i]<=0;end
        else begin
            if(reg_wr) begin reg_ready<=1;case(reg_addr[7:0])
                8'h00:target<=reg_wdata[7:0];
                8'h04:if(reg_wdata[0]) begin progs_tried<=0;halt_count<=0;match_count<=0;
                    enumeration_done<=0;load_idx<=0;for(int i=0;i<8;i=i+1)cur_d[i]<=0;state<=S_LOAD;end
                8'h40:isa_lut_reg<=reg_wdata[23:0];default:;endcase end
            if(reg_rd) begin reg_ready<=1;case(reg_addr[7:0])
                8'h08:reg_rdata<={29'd0,enumeration_done,1'b0,state!=S_IDLE&&state!=S_DONE};
                8'h28:reg_rdata<=progs_tried;8'h34:reg_rdata<=halt_count;
                default:reg_rdata<=0;endcase end
            case(state)
                S_LOAD:begin if(enumeration_done)state<=S_DONE;else begin
                    interp_prog[load_idx]<=pack_digits(cur_d[7],cur_d[6],cur_d[5],cur_d[4],cur_d[3],cur_d[2],cur_d[1],cur_d[0]);
                    begin logic [24:0] nxt;nxt=base6_inc(cur_d[7],cur_d[6],cur_d[5],cur_d[4],cur_d[3],cur_d[2],cur_d[1],cur_d[0]);
                        cur_d[0]<=nxt[2:0];
                        cur_d[1]<=nxt[5:3];
                        cur_d[2]<=nxt[8:6];
                        cur_d[3]<=nxt[11:9];
                        cur_d[4]<=nxt[14:12];
                        cur_d[5]<=nxt[17:15];
                        cur_d[6]<=nxt[20:18];
                        cur_d[7]<=nxt[23:21];
                        if(nxt[24])enumeration_done<=1;end
                    if(load_idx>=N_INTERP-1)begin interp_start<=1;run_timer<=0;state<=S_RUN;end else load_idx<=load_idx+1;end end
                S_RUN:begin run_timer<=run_timer+1;all_done=1;for(int i=0;i<N_INTERP;i=i+1)if(!interp_done[i])all_done=0;
                    if(all_done||run_timer>=65546)begin collect_idx<=0;state<=S_COLLECT;end end
                S_COLLECT:begin if(collect_idx<N_INTERP)begin
                    if(interp_halted[collect_idx])begin halt_count<=halt_count+1;
                        if(interp_result[collect_idx]=={(16){1'b0}})match_count<=match_count+1;end
                    collect_idx<=collect_idx+1;end else begin progs_tried<=progs_tried+N_INTERP;
                    if(enumeration_done||progs_tried+N_INTERP>=1679616)state<=S_DONE;
                    else begin load_idx<=0;state<=S_LOAD;end end end
                S_DONE:;default:;endcase end end endmodule
