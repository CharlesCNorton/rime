#!/usr/bin/env python3
"""Generate width-parameterized experiment.
Two ISAs (A and B) at register widths 8,10,12,14,16.
One run per width (firmware reconfigures ISA LUT between A and B).
"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent.parent / "modules" / "rime-i"))
from gen_firmware import RV32I

Q = "'"

def write_interp(width):
    """Write a width-parameterized interpreter."""
    W = width
    TMAX = 1 << W
    L = []
    def a(s): L.append(s)
    a(f"module tiny_interp_w{W} (")
    a(f"    input wire clk,input wire rst,input wire start,")
    a(f"    input wire [23:0] program,input wire [{W-1}:0] init_a,input wire [{W-1}:0] init_b,")
    a(f"    input wire [23:0] isa_lut,")
    a(f"    output logic [{W-1}:0] result,output logic done,output logic halted);")
    a(f"    localparam integer MAX_STEPS={TMAX},PROG_LEN=8;")
    a(f"    logic [{W-1}:0] a,b;logic [3:0] pc;logic [{max(8,W.bit_length()+1)}:0] step;logic running;")
    a(f"    logic [2:0] raw_op;")
    a(f"    always_comb case(pc)")
    for i in range(8):
        a(f"        4{Q}d{i}:raw_op=program[{i*3+2}:{i*3}];")
    a(f"        default:raw_op=3{Q}d5;endcase")
    a(f"    logic [3:0] op_id;")
    a(f"    always_comb case(raw_op)")
    for i in range(6):
        a(f"        3{Q}d{i}:op_id=isa_lut[{i*4+3}:{i*4}];")
    a(f"        default:op_id=4{Q}d14;endcase")
    a(f"    always_ff @(posedge clk) begin done<=0;")
    a(f"        if(rst) begin running<=0;a<=0;b<=0;pc<=0;step<=0;result<=0;halted<=0;end")
    a(f"        else if(start) begin running<=1;a<=init_a;b<=init_b;pc<=0;step<=0;halted<=0;end")
    a(f"        else if(running) begin")
    a(f"            if(pc>=PROG_LEN) begin result<=a;halted<=1;done<=1;running<=0;end")
    a(f"            else if(step>=MAX_STEPS) begin result<=a;halted<=0;done<=1;running<=0;end")
    a(f"            else begin step<=step+1;case(op_id)")
    a(f"                0:begin a<=a+1;pc<=pc+1;end")
    a(f"                1:begin a<=a-1;pc<=pc+1;end")
    a(f"                2:begin a<=b;b<=a;pc<=pc+1;end")
    a(f"                3:begin a<=a+b;pc<=pc+1;end")
    a(f"                4:begin a<=a^b;pc<=pc+1;end")
    a(f"                5:begin if(a!=0)pc<=0;else pc<=pc+1;end")
    a(f"                6:begin a<=-a;pc<=pc+1;end")
    a(f"                7:begin b<=a;pc<=pc+1;end")
    a(f"                8:begin a<=a-b;pc<=pc+1;end")
    a(f"                9:begin a<=a&b;pc<=pc+1;end")
    a(f"                10:begin a<=a|b;pc<=pc+1;end")
    a(f"                11:begin a<=a>>1;pc<=pc+1;end")
    a(f"                12:begin a<={{a[{W-2}:0],1{Q}b0}};pc<=pc+1;end")
    a(f"                13:begin a<=~a;pc<=pc+1;end")
    a(f"                14:begin pc<=pc+1;end")
    a(f"                15:begin result<=a;halted<=1;done<=1;running<=0;end")
    a(f"            endcase end end end endmodule")
    fname = f"tiny_interp_w{W}.sv"
    (BASE / fname).write_text("\n".join(L) + "\n")
    print(f"wrote {fname}")

def write_ctrl(width):
    """Write controller for width W interpreter."""
    W = width
    TMAX = 1 << W
    L = []
    def a(s): L.append(s)
    a(f"module width_ctrl_{W} #(parameter integer N_INTERP=16) (")
    a(f"    input wire clk,input wire rst,input wire [11:0] reg_addr,input wire [31:0] reg_wdata,")
    a(f"    input wire reg_wr,input wire reg_rd,(* keep *) output logic [31:0] reg_rdata,(* keep *) output logic reg_ready);")
    a(f"    logic interp_start;logic [23:0] interp_prog[0:N_INTERP-1];")
    a(f"    logic [{W-1}:0] interp_result[0:N_INTERP-1];logic interp_done[0:N_INTERP-1];logic interp_halted[0:N_INTERP-1];")
    a(f"    logic [{W-1}:0] init_a_reg,init_b_reg;logic [23:0] isa_lut_reg;")
    a(f"    genvar gi;generate for(gi=0;gi<N_INTERP;gi=gi+1) begin:gen_interp")
    a(f"        tiny_interp_w{W} I(.clk(clk),.rst(rst),.start(interp_start),")
    a(f"            .program(interp_prog[gi]),.init_a(init_a_reg),.init_b(init_b_reg),")
    a(f"            .isa_lut(isa_lut_reg),.result(interp_result[gi]),.done(interp_done[gi]),.halted(interp_halted[gi]));")
    a(f"    end endgenerate")
    # Base-6 odometer + FSM (same as omega_ctrl)
    a(f"    logic [2:0] cur_d[0:7];")
    a(f"    function automatic [24:0] base6_inc(input [2:0] d7,d6,d5,d4,d3,d2,d1,d0);")
    a(f"        logic [2:0] r[0:7];logic c;r[0]=d0+1;c=(d0==5);if(c)r[0]=0;")
    for i in range(1, 8):
        a(f"        r[{i}]=c?d{i}+1:d{i};if(c&&d{i}==5)begin r[{i}]=0;c=1;end else c=0;")
    a(f"        base6_inc={{c,r[7],r[6],r[5],r[4],r[3],r[2],r[1],r[0]}};endfunction")
    a(f"    function automatic [23:0] pack_digits(input [2:0] d7,d6,d5,d4,d3,d2,d1,d0);")
    a(f"        pack_digits={{d7,d6,d5,d4,d3,d2,d1,d0}};endfunction")
    a(f"    logic [7:0] target;logic [3:0] search_len;")
    a(f"    localparam [2:0] S_IDLE=0,S_LOAD=1,S_RUN=2,S_COLLECT=3,S_DONE=4;")
    a(f"    (* keep *) logic [2:0] state;(* keep *) logic [31:0] progs_tried,halt_count,match_count;")
    a(f"    (* keep *) logic [{max(9, (TMAX-1).bit_length())}:0] run_timer;(* keep *) logic all_done;")
    a(f"    logic enumeration_done;logic [4:0] load_idx,collect_idx;")
    a(f"    always_ff @(posedge clk) begin reg_ready<=0;interp_start<=0;")
    a(f"        if(rst) begin state<=S_IDLE;progs_tried<=0;halt_count<=0;match_count<=0;")
    a(f"            enumeration_done<=0;init_a_reg<=0;init_b_reg<=0;search_len<=8;target<=0;")
    a(f"            isa_lut_reg<=24{Q}h543210;for(int i=0;i<8;i=i+1)cur_d[i]<=0;end")
    a(f"        else begin")
    a(f"            if(reg_wr) begin reg_ready<=1;case(reg_addr[7:0])")
    a(f"                8{Q}h00:target<=reg_wdata[7:0];")
    a(f"                8{Q}h04:if(reg_wdata[0]) begin progs_tried<=0;halt_count<=0;match_count<=0;")
    a(f"                    enumeration_done<=0;load_idx<=0;for(int i=0;i<8;i=i+1)cur_d[i]<=0;state<=S_LOAD;end")
    a(f"                8{Q}h40:isa_lut_reg<=reg_wdata[23:0];default:;endcase end")
    a(f"            if(reg_rd) begin reg_ready<=1;case(reg_addr[7:0])")
    a(f"                8{Q}h08:reg_rdata<={{29{Q}d0,enumeration_done,1{Q}b0,state!=S_IDLE&&state!=S_DONE}};")
    a(f"                8{Q}h28:reg_rdata<=progs_tried;8{Q}h34:reg_rdata<=halt_count;")
    a(f"                default:reg_rdata<=0;endcase end")
    a(f"            case(state)")
    a(f"                S_LOAD:begin if(enumeration_done)state<=S_DONE;else begin")
    a(f"                    interp_prog[load_idx]<=pack_digits(cur_d[7],cur_d[6],cur_d[5],cur_d[4],cur_d[3],cur_d[2],cur_d[1],cur_d[0]);")
    a(f"                    begin logic [24:0] nxt;nxt=base6_inc(cur_d[7],cur_d[6],cur_d[5],cur_d[4],cur_d[3],cur_d[2],cur_d[1],cur_d[0]);")
    for i in range(8):
        a(f"                        cur_d[{i}]<=nxt[{i*3+2}:{i*3}];")
    a(f"                        if(nxt[24])enumeration_done<=1;end")
    a(f"                    if(load_idx>=N_INTERP-1)begin interp_start<=1;run_timer<=0;state<=S_RUN;end else load_idx<=load_idx+1;end end")
    a(f"                S_RUN:begin run_timer<=run_timer+1;all_done=1;for(int i=0;i<N_INTERP;i=i+1)if(!interp_done[i])all_done=0;")
    a(f"                    if(all_done||run_timer>={TMAX+10})begin collect_idx<=0;state<=S_COLLECT;end end")
    a(f"                S_COLLECT:begin if(collect_idx<N_INTERP)begin")
    a(f"                    if(interp_halted[collect_idx])begin halt_count<=halt_count+1;")
    a(f"                        if(interp_result[collect_idx]=={{({W}){{1{Q}b0}}}})match_count<=match_count+1;end")
    a(f"                    collect_idx<=collect_idx+1;end else begin progs_tried<=progs_tried+N_INTERP;")
    a(f"                    if(enumeration_done||progs_tried+N_INTERP>=1679616)state<=S_DONE;")
    a(f"                    else begin load_idx<=0;state<=S_LOAD;end end end")
    a(f"                S_DONE:;default:;endcase end end endmodule")
    fname = f"width_ctrl_{W}.sv"
    (BASE / fname).write_text("\n".join(L) + "\n")
    print(f"wrote {fname}")

def write_top_and_firmware(widths):
    """Write top.sv with one controller per width, firmware sweeps ISA-A then ISA-B for each."""
    L = []
    def a(s): L.append(s)
    mods = [(f"W{w}", w, 16, 0x30 + i) for i, w in enumerate(widths)]

    a("module top(input wire clk,input wire usb_rx,output wire usb_tx,output logic [4:0] led,input wire [1:0] button,")
    a("    output wire flash_csn,output wire flash_mosi,output wire flash_wpn,output wire flash_resetn,input wire flash_miso,")
    a("    output wire sd_clk,output wire sd_csn,output wire sd_mosi,input wire sd_miso,input wire sd_det,")
    a("    output wire sdram_clk,output wire sdram_cke,output wire sdram_csn,output wire sdram_rasn,output wire sdram_casn,output wire sdram_wen,")
    a(f"    output wire [1:0] sdram_ba,output wire [12:0] sdram_a,inout wire [15:0] sdram_dq,output wire [1:0] sdram_dqm);")
    a(f"    assign flash_csn=1;assign flash_mosi=0;assign flash_wpn=1;assign flash_resetn=1;")
    a(f"    assign sd_clk=0;assign sd_csn=1;assign sd_mosi=1;assign sdram_clk=0;assign sdram_cke=0;assign sdram_csn=1;")
    a(f"    assign sdram_rasn=1;assign sdram_casn=1;assign sdram_wen=1;assign sdram_ba=0;assign sdram_a=0;assign sdram_dqm=2{Q}b11;")
    a("    localparam integer CLK_HZ=25000000,BAUD=115200,MEM_WORDS=1024;")
    a("    logic sys_clk;always_ff @(posedge clk) begin if(~button[0])sys_clk<=0;else sys_clk<=~sys_clk;end")
    a("    logic [3:0] sc;logic sd;always_ff @(posedge sys_clk) begin if(~button[0])begin sc<=0;sd<=0;end else if(!sd)begin if(sc==15)sd<=1;else sc<=sc+1;end end")
    a("    wire rst=~button[0]||!sd;wire [31:0] mem_addr,mem_wdata;wire [3:0] mem_wstrb;wire mem_valid;reg [31:0] mem_rdata;reg mem_ready;wire [31:0] dbg_reg10;")
    a("    rime_i_core CPU(.clk(sys_clk),.rst(rst),.mem_addr(mem_addr),.mem_wdata(mem_wdata),.mem_wstrb(mem_wstrb),.mem_valid(mem_valid),.mem_rdata(mem_rdata),.mem_ready(mem_ready),.dbg_reg10(dbg_reg10));")
    a(f"    (* ram_style=\"block\" *) reg [31:0] bram[0:MEM_WORDS-1];wire [$clog2(MEM_WORDS)-1:0] bram_idx=mem_addr[$clog2(MEM_WORDS)+1:2];")
    a(f"    wire is_bram=(mem_addr[31:28]==4{Q}h0);wire is_uart=(mem_addr[31:28]==4{Q}h2);")
    for nm, w, ni, ad in mods:
        a(f"    wire is_{nm}=(mem_addr[31:24]==8{Q}h{ad:02X});")
    a("    always_ff @(posedge sys_clk) begin if(is_bram&&mem_valid&&mem_wstrb!=0) begin")
    a("        if(mem_wstrb[0])bram[bram_idx][7:0]<=mem_wdata[7:0];if(mem_wstrb[1])bram[bram_idx][15:8]<=mem_wdata[15:8];")
    a("        if(mem_wstrb[2])bram[bram_idx][23:16]<=mem_wdata[23:16];if(mem_wstrb[3])bram[bram_idx][31:24]<=mem_wdata[31:24];end end")
    a("    wire [31:0] bram_rdata=bram[bram_idx];reg tx_send;reg [7:0] tx_byte;reg [15:0] tx_busy_cnt;wire tx_busy=(tx_busy_cnt!=0);")
    a("    localparam integer UCC=((CLK_HZ/BAUD)*11);")
    a("    uart_tx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) UTX(.clk(sys_clk),.send(tx_send),.data(tx_byte),.tx(usb_tx));")
    a("    always_ff @(posedge sys_clk) begin if(rst)tx_busy_cnt<=0;else if(tx_send)tx_busy_cnt<=UCC[15:0];else if(tx_busy_cnt!=0)tx_busy_cnt<=tx_busy_cnt-1;end")
    a("    wire rx_valid;wire [7:0] rx_data;reg rx_pending;reg [7:0] rx_byte;")
    a("    uart_rx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) URX(.clk(sys_clk),.rx(usb_rx),.finish(rx_valid),.data(rx_data));")
    a(f"    always_ff @(posedge sys_clk) begin if(rst)rx_pending<=0;else begin if(rx_valid)begin rx_byte<=rx_data;rx_pending<=1;end")
    a(f"        if(is_uart&&mem_valid&&mem_ready&&mem_wstrb==0&&mem_addr[3:0]==4{Q}h8)rx_pending<=0;end end")
    for nm, w, ni, ad in mods:
        a(f"    wire [31:0] {nm}_rd;wire {nm}_rdy;width_ctrl_{w} #(.N_INTERP({ni})) {nm}(.clk(sys_clk),.rst(rst),")
        a(f"        .reg_addr(mem_addr[11:0]),.reg_wdata(mem_wdata),.reg_wr(is_{nm}&&mem_valid&&!mem_ready&&!{nm}_rdy&&mem_wstrb!=0),")
        a(f"        .reg_rd(is_{nm}&&mem_valid&&!mem_ready&&!{nm}_rdy&&mem_wstrb==0),.reg_rdata({nm}_rd),.reg_ready({nm}_rdy));")
    a("    always_ff @(posedge sys_clk) begin tx_send<=0;mem_ready<=0;if(!rst&&mem_valid&&!mem_ready) begin")
    a("        if(is_bram)begin mem_rdata<=bram_rdata;mem_ready<=1;end")
    a(f"        else if(is_uart)begin case(mem_addr[3:0])")
    a(f"            4{Q}h0:begin if(mem_wstrb!=0&&!tx_busy)begin tx_byte<=mem_wdata[7:0];tx_send<=1;mem_ready<=1;end else if(mem_wstrb==0)begin mem_rdata<=0;mem_ready<=1;end end")
    a(f"            4{Q}h4:begin mem_rdata<={{31{Q}d0,tx_busy}};mem_ready<=1;end 4{Q}h8:begin mem_rdata<={{24{Q}d0,rx_byte}};mem_ready<=1;end")
    a(f"            4{Q}hC:begin mem_rdata<={{31{Q}d0,rx_pending}};mem_ready<=1;end default:begin mem_rdata<=0;mem_ready<=1;end endcase end")
    for nm, w, ni, ad in mods:
        a(f"        else if(is_{nm})begin if({nm}_rdy)begin mem_rdata<={nm}_rd;mem_ready<=1;end end")
    a("        else begin mem_rdata<=0;mem_ready<=1;end end end")
    a(f'    assign led=dbg_reg10[4:0];initial $readmemh("firmware.hex",bram);endmodule')
    (BASE / "top.sv").write_text("\n".join(L) + "\n")
    print(f"wrote top.sv ({len(mods)} width modules)")

    # Firmware: for each width module, run ISA-A then ISA-B, print results
    ISA_A = 0x543210
    ISA_B = 0x598760
    x0,ra,sp = 0,1,2; t0,t1,t2,t3 = 5,6,7,28; a0,a1 = 10,11
    s0,s1,s2,s3,s4,s5,s6,s7 = 8,9,18,19,20,21,22,23
    UART = 0x20000000
    f = RV32I()
    f.lui(sp, 0x00001); f.lui(s5, UART >> 12); f.j("main")
    f.label("putc"); f.lw(t0,s5,4); f.bne(t0,x0,"putc"); f.sw(a0,s5,0); f.ret()
    f.label("puthex"); f.addi(sp,sp,-8); f.sw(ra,sp,4); f.sw(s0,sp,0)
    f.mv(s0,a0); f.addi(s1,x0,28)
    f.label("ph_l"); f.blt(s1,x0,"ph_x"); f.srl(a0,s0,s1); f.andi(a0,a0,0xF); f.addi(t0,x0,10)
    f.blt(a0,t0,"ph_d"); f.addi(a0,a0,55); f.j("ph_e")
    f.label("ph_d"); f.addi(a0,a0,48)
    f.label("ph_e"); f.call("putc"); f.addi(s1,s1,-4); f.j("ph_l")
    f.label("ph_x"); f.lw(s0,sp,0); f.lw(ra,sp,4); f.addi(sp,sp,8); f.ret()
    # run_mod: s6=base, runs search, prints halt_count
    f.label("run_mod"); f.addi(sp,sp,-4); f.sw(ra,sp,0)
    f.sw(x0,s6,0x00); f.addi(t0,x0,1); f.sw(t0,s6,0x04)
    f.label("rm_w"); f.lw(t0,s6,0x08); f.andi(t0,t0,1); f.bne(t0,x0,"rm_w")
    f.lw(a0,s6,0x34); f.call("puthex"); f.addi(a0,x0,10); f.call("putc")
    f.lw(ra,sp,0); f.addi(sp,sp,4); f.ret()

    f.label("main")
    for ch in "WSCALE\r\n": f.addi(a0,x0,ord(ch)); f.call("putc")

    for nm, w, ni, ad in mods:
        # Print width tag
        for ch in f"W{w:02d}:": f.addi(a0,x0,ord(ch)); f.call("putc")
        f.lui(s6, ad << 20)
        # ISA-A
        f.li(t0, ISA_A); f.sw(t0, s6, 0x40)
        f.call("run_mod")
        # ISA-B
        f.li(t0, ISA_B); f.sw(t0, s6, 0x40)
        f.call("run_mod")

    for ch in "DONE\r\n": f.addi(a0,x0,ord(ch)); f.call("putc")
    f.li(t0, 0x4000000); f.label("_d"); f.addi(t0,t0,-1); f.bne(t0,x0,"_d"); f.j("main")
    f.resolve()
    print(f"Firmware: {len(f.code)} instructions")
    assert len(f.code) <= 1024
    with open(BASE / "firmware.hex", "w") as fh:
        for i in range(1024):
            fh.write(f"{f.code[i] if i < len(f.code) else 0x00000013:08x}\n")
    print("wrote firmware.hex")

def cleanup():
    for old in ["kolmogorov200pf.sv","kolmogorov200pfb.sv","tiny_interp.sv","tiny_interp_pf.sv",
                "tiny_interp_pfb.sv","_gen_unified.py","_gen_tm3.py"]:
        p = BASE / old
        if p.exists(): p.unlink()
    print("Files:", sorted(p.name for p in BASE.glob("*.sv")))

if __name__ == "__main__":
    widths = [8, 10, 12, 14, 16]
    for w in widths:
        write_interp(w)
        write_ctrl(w)
    write_top_and_firmware(widths)
    cleanup()
