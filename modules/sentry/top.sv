// SENTRY compositor test: RIME-I + SENTRY
module top (
    input  wire        clk,
    input  wire        usb_rx,
    output wire        usb_tx,
    output logic [4:0] led,
    input  wire [1:0]  button,
    output wire        flash_csn, output wire flash_mosi,
    output wire        flash_wpn, output wire flash_resetn,
    input  wire        flash_miso,
    output wire        sd_clk, output wire sd_csn, output wire sd_mosi,
    input  wire        sd_miso, input wire sd_det,
    output wire        sdram_clk, output wire sdram_cke,
    output wire        sdram_csn, output wire sdram_rasn,
    output wire        sdram_casn, output wire sdram_wen,
    output wire [1:0]  sdram_ba, output wire [12:0] sdram_a,
    inout  wire [15:0] sdram_dq, output wire [1:0] sdram_dqm
);
    assign flash_csn=1; assign flash_mosi=0; assign flash_wpn=1; assign flash_resetn=1;
    assign sd_clk=0; assign sd_csn=1; assign sd_mosi=1;
    assign sdram_clk=0; assign sdram_cke=0; assign sdram_csn=1;
    assign sdram_rasn=1; assign sdram_casn=1; assign sdram_wen=1;
    assign sdram_ba=0; assign sdram_a=0; assign sdram_dqm=2'b11;

    localparam integer CLK_HZ = 25000000;
    localparam integer BAUD = 115200;
    localparam integer MEM_WORDS = 1024;

    logic sys_clk;
    always_ff @(posedge clk) begin
        if (~button[0]) sys_clk <= 0; else sys_clk <= ~sys_clk;
    end
    logic [3:0] sc; logic sd;
    always_ff @(posedge sys_clk) begin
        if (~button[0]) begin sc<=0; sd<=0; end
        else if (!sd) begin if (sc==15) sd<=1; else sc<=sc+1; end
    end
    wire rst = ~button[0] || !sd;

    wire [31:0] mem_addr, mem_wdata;
    wire [3:0] mem_wstrb; wire mem_valid;
    reg [31:0] mem_rdata; reg mem_ready;
    wire [31:0] dbg_reg10;
    rime_i_core CPU(.clk(sys_clk),.rst(rst),
        .mem_addr(mem_addr),.mem_wdata(mem_wdata),
        .mem_wstrb(mem_wstrb),.mem_valid(mem_valid),
        .mem_rdata(mem_rdata),.mem_ready(mem_ready),
        .dbg_reg10(dbg_reg10));

    reg [31:0] bram [0:MEM_WORDS-1];
    wire [$clog2(MEM_WORDS)-1:0] bram_idx = mem_addr[$clog2(MEM_WORDS)+1:2];
    wire is_bram = (mem_addr[31:28]==4'h0);
    wire is_uart = (mem_addr[31:28]==4'h2);
    wire is_mod  = (mem_addr[31:28]==4'h3);

    always_ff @(posedge sys_clk) begin
        if (is_bram && mem_valid && mem_wstrb!=0) begin
            if (mem_wstrb[0]) bram[bram_idx][7:0]<=mem_wdata[7:0];
            if (mem_wstrb[1]) bram[bram_idx][15:8]<=mem_wdata[15:8];
            if (mem_wstrb[2]) bram[bram_idx][23:16]<=mem_wdata[23:16];
            if (mem_wstrb[3]) bram[bram_idx][31:24]<=mem_wdata[31:24];
        end
    end
    wire [31:0] bram_rdata = bram[bram_idx];

    reg tx_send; reg [7:0] tx_byte;
    reg [15:0] tx_busy_cnt;
    wire tx_busy = (tx_busy_cnt!=0);
    localparam integer UCC = ((CLK_HZ/BAUD)*11);
    uart_tx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) UTX(.clk(sys_clk),.send(tx_send),.data(tx_byte),.tx(usb_tx));
    always_ff @(posedge sys_clk) begin
        if (rst) tx_busy_cnt<=0;
        else if (tx_send) tx_busy_cnt<=UCC[15:0];
        else if (tx_busy_cnt!=0) tx_busy_cnt<=tx_busy_cnt-1;
    end
    wire rx_valid; wire [7:0] rx_data;
    reg rx_pending; reg [7:0] rx_byte;
    uart_rx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) URX(.clk(sys_clk),.rx(usb_rx),.finish(rx_valid),.data(rx_data));
    always_ff @(posedge sys_clk) begin
        if (rst) rx_pending<=0;
        else begin
            if (rx_valid) begin rx_byte<=rx_data; rx_pending<=1; end
            if (is_uart&&mem_valid&&mem_ready&&mem_wstrb==0&&mem_addr[3:0]==4'h8) rx_pending<=0;
        end
    end

    wire [31:0] mod_rdata; wire mod_ready;
    sentry MOD(.clk(sys_clk),.rst(rst),
        .reg_addr(mem_addr[11:0]),.reg_wdata(mem_wdata),
        .reg_wr(is_mod&&mem_valid&&!mem_ready&&!mod_ready&&mem_wstrb!=0),
        .reg_rd(is_mod&&mem_valid&&!mem_ready&&!mod_ready&&mem_wstrb==0),
        .reg_rdata(mod_rdata),.reg_ready(mod_ready));

    always_ff @(posedge sys_clk) begin
        tx_send<=0; mem_ready<=0;
        if (!rst && mem_valid && !mem_ready) begin
            if (is_bram) begin mem_rdata<=bram_rdata; mem_ready<=1; end
            else if (is_uart) begin
                case(mem_addr[3:0])
                    4'h0: begin
                        if (mem_wstrb!=0 && !tx_busy) begin tx_byte<=mem_wdata[7:0]; tx_send<=1; mem_ready<=1; end
                        else if (mem_wstrb==0) begin mem_rdata<=0; mem_ready<=1; end
                    end
                    4'h4: begin mem_rdata<={31'd0,tx_busy}; mem_ready<=1; end
                    4'h8: begin mem_rdata<={24'd0,rx_byte}; mem_ready<=1; end
                    4'hC: begin mem_rdata<={31'd0,rx_pending}; mem_ready<=1; end
                    default: begin mem_rdata<=0; mem_ready<=1; end
                endcase
            end
            else if (is_mod) begin
                if (mod_ready) begin mem_rdata<=mod_rdata; mem_ready<=1; end
            end
            else begin mem_rdata<=0; mem_ready<=1; end
        end
    end
    assign led = dbg_reg10[4:0];
    initial begin
        integer _i;
        for (_i=0;_i<MEM_WORDS;_i=_i+1) bram[_i]=32'h00000013;
        bram[0] = 32'h00001137;
        bram[1] = 32'h20000a37;
        bram[2] = 32'h0140006f;
        bram[3] = 32'h004a2283;
        bram[4] = 32'hfe029ee3;
        bram[5] = 32'h00aa2023;
        bram[6] = 32'h00008067;
        bram[7] = 32'h300002b7;
        bram[8] = 32'h01028293;
        bram[9] = 32'h0002a023;
        bram[10] = 32'h300002b7;
        bram[11] = 32'h0000a337;
        bram[12] = 32'h99930313;
        bram[13] = 32'h0062a023;
        bram[14] = 32'h300002b7;
        bram[15] = 32'h00428293;
        bram[16] = 32'h00100313;
        bram[17] = 32'h0062a023;
        bram[18] = 32'h300002b7;
        bram[19] = 32'h00828293;
        bram[20] = 32'h0002a403;
        bram[21] = 32'h00147413;
        bram[22] = 32'h03100513;
        bram[23] = 32'hfb1ff0ef;
        bram[24] = 32'h00040863;
        bram[25] = 32'h05000513;
        bram[26] = 32'hfa5ff0ef;
        bram[27] = 32'h00c0006f;
        bram[28] = 32'h04600513;
        bram[29] = 32'hf99ff0ef;
        bram[30] = 32'h300002b7;
        bram[31] = 32'h02028293;
        bram[32] = 32'h00001337;
        bram[33] = 32'h0062a023;
        bram[34] = 32'h300002b7;
        bram[35] = 32'h02428293;
        bram[36] = 32'h00070337;
        bram[37] = 32'h10030313;
        bram[38] = 32'h0062a023;
        bram[39] = 32'h300002b7;
        bram[40] = 32'h01028293;
        bram[41] = 32'h00300313;
        bram[42] = 32'h0062a023;
        bram[43] = 32'h300002b7;
        bram[44] = 32'h00001337;
        bram[45] = 32'h08030313;
        bram[46] = 32'h0062a023;
        bram[47] = 32'h300002b7;
        bram[48] = 32'h00428293;
        bram[49] = 32'h00100313;
        bram[50] = 32'h0062a023;
        bram[51] = 32'h300002b7;
        bram[52] = 32'h00828293;
        bram[53] = 32'h0002a403;
        bram[54] = 32'h00147413;
        bram[55] = 32'h300002b7;
        bram[56] = 32'h00002337;
        bram[57] = 32'h0062a023;
        bram[58] = 32'h300002b7;
        bram[59] = 32'h00428293;
        bram[60] = 32'h00100313;
        bram[61] = 32'h0062a023;
        bram[62] = 32'h300002b7;
        bram[63] = 32'h00828293;
        bram[64] = 32'h0002a483;
        bram[65] = 32'h0014f493;
        bram[66] = 32'h03200513;
        bram[67] = 32'hf01ff0ef;
        bram[68] = 32'h00040a63;
        bram[69] = 32'h00049863;
        bram[70] = 32'h05000513;
        bram[71] = 32'hef1ff0ef;
        bram[72] = 32'h00c0006f;
        bram[73] = 32'h04600513;
        bram[74] = 32'hee5ff0ef;
        bram[75] = 32'h300002b7;
        bram[76] = 32'h00828293;
        bram[77] = 32'h0002a403;
        bram[78] = 32'h00247413;
        bram[79] = 32'h300002b7;
        bram[80] = 32'h00c28293;
        bram[81] = 32'h0002a483;
        bram[82] = 32'h03300513;
        bram[83] = 32'hec1ff0ef;
        bram[84] = 32'h00040c63;
        bram[85] = 32'h000022b7;
        bram[86] = 32'h00549863;
        bram[87] = 32'h05000513;
        bram[88] = 32'headff0ef;
        bram[89] = 32'h00c0006f;
        bram[90] = 32'h04600513;
        bram[91] = 32'hea1ff0ef;
        bram[92] = 32'h00a00513;
        bram[93] = 32'he99ff0ef;
        bram[94] = 32'h002002b7;
        bram[95] = 32'hfff28293;
        bram[96] = 32'hfe029ee3;
        bram[97] = 32'he99ff06f;
    end
endmodule
