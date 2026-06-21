// Experiment 25: Kolmogorov / Solomonoff / Omega — 200 parallel interpreters.
//
// Sweeps the full program space (length 6: 46,656 programs, length 8: 1,679,616)
// using 200 interpreters in parallel. Each batch: 200 programs execute simultaneously,
// the CPU collects halt/output results and accumulates:
//   K(target): length of shortest program that outputs target
//   P(x): fraction of halting programs that output x (algorithmic probability)
//   Omega: fraction of programs that halt (halting probability)
//
// The KOLMOGOROV module handles the interpreter array and enumeration.
// The CPU firmware drives the search and prints results over UART.

module top (
    input  wire       clk,
    input  wire       usb_rx,
    output wire       usb_tx,
    output logic [4:0] led,
    input  wire [1:0] button,
    output wire flash_csn, output wire flash_mosi,
    output wire flash_wpn, output wire flash_resetn,
    input  wire flash_miso,
    output wire sd_clk, output wire sd_csn, output wire sd_mosi,
    input  wire sd_miso, input wire sd_det,
    output wire sdram_clk, output wire sdram_cke, output wire sdram_csn,
    output wire sdram_rasn, output wire sdram_casn, output wire sdram_wen,
    output wire [1:0] sdram_ba, output wire [12:0] sdram_a,
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

    (* ram_style = "block" *) reg [31:0] bram [0:MEM_WORDS-1];
    wire [$clog2(MEM_WORDS)-1:0] bram_idx = mem_addr[$clog2(MEM_WORDS)+1:2];
    wire is_bram = (mem_addr[31:28]==4'h0);
    wire is_uart = (mem_addr[31:28]==4'h2);
    // is_mod removed — replaced by is_mod_a and is_mod_b below

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

    // Single module: prefix-free ISA at 0x30 (uses kolmogorov200 which instantiates tiny_interp)
    wire is_mod  = (mem_addr[31:28] == 4'h3);

    wire [31:0] mod_rdata; wire mod_ready;
    kolmogorov200 MOD(.clk(sys_clk),.rst(rst),
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
    initial $readmemh("firmware.hex", bram);
endmodule
