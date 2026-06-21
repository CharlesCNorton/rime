// Self-referential complexity collapse: RIME-I + KOLMOGOROV.
// BRAM initialized with seed pattern; ecpbram patches real firmware post-synthesis.
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
    assign sdram_dq=16'bz;

    localparam integer CLK_HZ = 12500000;
    localparam integer BAUD = 115200;
    localparam integer MEM_WORDS = 1024;

    // sys_clk = 12.5 MHz (clk/4) for timing margin with KOLMOGOROV's
    // deep combinational paths. The 25 MHz divider (clk/2) doesn't meet
    // timing for the 10-interpreter all_done reduction + bus decode.
    logic [1:0] clk_div = 0;
    wire sys_clk = clk_div[1];
    always_ff @(posedge clk) begin
        if (~button[0]) clk_div <= 0; else clk_div <= clk_div + 1;
    end
    logic [3:0] sc = 0; logic sd = 0;
    always_ff @(posedge sys_clk) begin
        if (~button[0]) begin sc<=0; sd<=0; end
        else if (!sd) begin if (sc==15) sd<=1; else sc<=sc+1; end
    end
    wire rst = ~button[0] || !sd;

    // CPU
    wire [31:0] mem_addr, mem_wdata;
    wire [3:0] mem_wstrb; wire mem_valid;
    reg [31:0] mem_rdata; reg mem_ready;
    wire [31:0] dbg_reg10;
    rime_i_core CPU(.clk(sys_clk),.rst(rst),
        .mem_addr(mem_addr),.mem_wdata(mem_wdata),
        .mem_wstrb(mem_wstrb),.mem_valid(mem_valid),
        .mem_rdata(mem_rdata),.mem_ready(mem_ready),
        .dbg_reg10(dbg_reg10));

    // BRAM — seed pattern for ecpbram patching
    (* ram_style = "block" *)
    reg [31:0] bram [0:MEM_WORDS-1];
    wire [9:0] bram_idx = mem_addr[11:2];
    wire is_bram = (mem_addr[31:28]==4'h0);
    wire is_uart = (mem_addr[31:28]==4'h2);
    wire is_kolm = (mem_addr[31:24]==8'h30);

    always_ff @(posedge sys_clk) begin
        if (is_bram && mem_valid && mem_wstrb!=0) begin
            if (mem_wstrb[0]) bram[bram_idx][7:0]   <= mem_wdata[7:0];
            if (mem_wstrb[1]) bram[bram_idx][15:8]  <= mem_wdata[15:8];
            if (mem_wstrb[2]) bram[bram_idx][23:16] <= mem_wdata[23:16];
            if (mem_wstrb[3]) bram[bram_idx][31:24] <= mem_wdata[31:24];
        end
    end
    wire [31:0] bram_rdata = bram[bram_idx];

    // BRAM init: LFSR seed pattern. ecpbram replaces this post-synthesis.
    // For synthesis: use bram_seed.hex (LFSR pattern for ecpbram matching).
    // For simulation: change to firmware_real.hex.
    initial $readmemh("bram_seed.hex", bram);

    // UART
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
    uart_rx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) URX(.clk(sys_clk),.rx(usb_rx),.finish(rx_valid),.data(rx_data));

    // KOLMOGOROV module
    wire [31:0] kolm_rdata; wire kolm_ready;
    kolmogorov KOLM_MOD(.clk(sys_clk),.rst(rst),
        .reg_addr(mem_addr[11:0]),.reg_wdata(mem_wdata),
        .reg_wr(is_kolm && mem_valid && !mem_ready && !kolm_ready && mem_wstrb!=0),
        .reg_rd(is_kolm && mem_valid && !mem_ready && !kolm_ready && mem_wstrb==0),
        .reg_rdata(kolm_rdata),.reg_ready(kolm_ready));

    // Bus response mux — combinational BRAM read (force distributed RAM)
    always_ff @(posedge sys_clk) begin
        tx_send <= 0; mem_ready <= 0;
        if (!rst && mem_valid && !mem_ready) begin
            if (is_bram) begin mem_rdata <= bram_rdata; mem_ready <= 1; end
            else if (is_uart) begin
                case (mem_addr[3:0])
                    4'h0: begin
                        if (mem_wstrb!=0 && !tx_busy) begin tx_byte<=mem_wdata[7:0]; tx_send<=1; mem_ready<=1; end
                        else if (mem_wstrb==0) begin mem_rdata<=0; mem_ready<=1; end
                    end
                    4'h4: begin mem_rdata<={31'd0,tx_busy}; mem_ready<=1; end
                    default: begin mem_rdata<=0; mem_ready<=1; end
                endcase
            end
            else if (is_kolm) begin
                if (kolm_ready) begin mem_rdata<=kolm_rdata; mem_ready<=1; end
            end
            else begin mem_rdata<=0; mem_ready<=1; end
        end
    end

    assign led = dbg_reg10[4:0];
endmodule
