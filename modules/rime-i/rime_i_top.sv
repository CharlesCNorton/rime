// rime_i_top: SoC wrapper for standalone RIME-I testing.
//
// Instantiates rime_i_core with BRAM (firmware via $readmemh),
// UART TX/RX, and a simple memory-mapped bus. Used by the ISA
// torture test and slab tests to verify the CPU on silicon without
// the full RIME service stack.

module rime_i_top #(
    parameter integer CLK_HZ = 25000000,
    parameter integer BAUD   = 115200,
    parameter integer MEM_WORDS = 3328
) (
    input  wire        clk,
    input  wire        rst,

    output wire        uart_tx,
    input  wire        uart_rx
);

    wire [31:0] mem_addr;
    wire [31:0] mem_wdata;
    wire [3:0]  mem_wstrb;
    wire        mem_valid;
    reg  [31:0] mem_rdata;
    reg         mem_ready;

    wire [31:0] dbg_reg10;
    rime_i_core CPU (
        .clk(clk), .rst(rst),
        .mem_addr(mem_addr), .mem_wdata(mem_wdata),
        .mem_wstrb(mem_wstrb), .mem_valid(mem_valid),
        .mem_rdata(mem_rdata), .mem_ready(mem_ready),
        .dbg_reg10(dbg_reg10)
    );

    (* ram_style = "block" *) reg [31:0] bram [0:MEM_WORDS-1];
    wire [$clog2(MEM_WORDS)-1:0] bram_idx = mem_addr[$clog2(MEM_WORDS)+1:2];
    wire        is_bram = (mem_addr[31:28] == 4'h0);
    wire        is_io   = (mem_addr[31:28] == 4'h2);

    always_ff @(posedge clk) begin
        if (is_bram && mem_valid && mem_wstrb != 4'b0000) begin
            if (mem_wstrb[0]) bram[bram_idx][7:0]   <= mem_wdata[7:0];
            if (mem_wstrb[1]) bram[bram_idx][15:8]  <= mem_wdata[15:8];
            if (mem_wstrb[2]) bram[bram_idx][23:16] <= mem_wdata[23:16];
            if (mem_wstrb[3]) bram[bram_idx][31:24] <= mem_wdata[31:24];
        end
    end

    reg        tx_send;
    reg  [7:0] tx_byte;
    reg [15:0] tx_busy_cnt;
    wire       tx_busy = (tx_busy_cnt != 16'd0);
    localparam integer UART_CHAR_CLKS = ((CLK_HZ / BAUD) * 11);

    wire        final_tx_send;
    wire [7:0]  final_tx_byte;
    uart_tx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) UART_TX (
        .clk(clk), .send(final_tx_send), .data(final_tx_byte), .tx(uart_tx)
    );

    always_ff @(posedge clk) begin
        if (rst) tx_busy_cnt <= 16'd0;
        else if (final_tx_send) tx_busy_cnt <= UART_CHAR_CLKS[15:0];
        else if (tx_busy_cnt != 16'd0) tx_busy_cnt <= tx_busy_cnt - 16'd1;
    end

    wire       rx_valid;
    wire [7:0] rx_data;
    reg        rx_pending;
    reg  [7:0] rx_byte;

    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) UART_RX (
        .clk(clk), .rx(uart_rx), .finish(rx_valid), .data(rx_data)
    );

    always_ff @(posedge clk) begin
        if (rst) rx_pending <= 1'b0;
        else begin
            if (rx_valid) begin
                rx_byte    <= rx_data;
                rx_pending <= 1'b1;
            end
            if (is_io && mem_valid && mem_ready && mem_wstrb == 4'b0000 && mem_addr[3:0] == 4'h8)
                rx_pending <= 1'b0;
        end
    end

    // Registered memory response: 1-cycle latency for all accesses.
    // CPU must keep mem_valid high until mem_ready fires.
    wire [31:0] bram_rdata = bram[bram_idx];

    always_ff @(posedge clk) begin
        tx_send   <= 1'b0;
        mem_ready <= 1'b0;

        if (rst) begin
        end else if (mem_valid && !mem_ready) begin
            if (is_bram) begin
                mem_rdata <= bram_rdata;
                mem_ready <= 1'b1;
            end else if (is_io) begin
                case (mem_addr[3:0])
                    4'h0: begin
                        if (mem_wstrb != 4'b0000 && !tx_busy) begin
                            tx_byte   <= mem_wdata[7:0];
                            tx_send   <= 1'b1;
                            mem_ready <= 1'b1;
                        end else if (mem_wstrb == 4'b0000) begin
                            mem_rdata <= 32'd0;
                            mem_ready <= 1'b1;
                        end
                    end
                    4'h4: begin mem_rdata <= {31'd0, tx_busy}; mem_ready <= 1'b1; end
                    4'h8: begin mem_rdata <= {24'd0, rx_byte}; mem_ready <= 1'b1; end
                    4'hC: begin mem_rdata <= {31'd0, rx_pending}; mem_ready <= 1'b1; end
                    default: begin mem_rdata <= 32'd0; mem_ready <= 1'b1; end
                endcase
            end else begin
                mem_rdata <= 32'd0;
                mem_ready <= 1'b1;
            end
        end
    end

    assign final_tx_send = tx_send;
    assign final_tx_byte = tx_byte;

    initial begin
        integer _i;
        for (_i = 0; _i < MEM_WORDS; _i = _i + 1)
            bram[_i] = 32'h00000013;
        $readmemh("firmware.hex", bram);
        bram[0] = 32'h00003137;
        bram[1] = 32'h40010113;
        bram[2] = 32'h20000a37;
        bram[3] = 32'h0140006f;
        bram[4] = 32'h004a2283;
        bram[5] = 32'hfe029ee3;
        bram[6] = 32'h00aa2023;
        bram[7] = 32'h00008067;
        bram[8] = 32'h14000413;
        bram[9] = 32'h000014b7;
        bram[10] = 32'hc9048493;
        bram[11] = 32'h00000913;
        bram[12] = 32'h02995663;
        bram[13] = 32'h00591293;
        bram[14] = 32'h00291313;
        bram[15] = 32'h006282b3;
        bram[16] = 32'h012282b3;
        bram[17] = 32'h0a528293;
        bram[18] = 32'h00291313;
        bram[19] = 32'h00830333;
        bram[20] = 32'h00532023;
        bram[21] = 32'h00190913;
        bram[22] = 32'hfd9ff06f;
        bram[23] = 32'h00000913;
        bram[24] = 32'h00000993;
        bram[25] = 32'h02995c63;
        bram[26] = 32'h00591293;
        bram[27] = 32'h00291313;
        bram[28] = 32'h006282b3;
        bram[29] = 32'h012282b3;
        bram[30] = 32'h0a528293;
        bram[31] = 32'h00291313;
        bram[32] = 32'h00830333;
        bram[33] = 32'h00032383;
        bram[34] = 32'h00729463;
        bram[35] = 32'h0080006f;
        bram[36] = 32'h00198993;
        bram[37] = 32'h00190913;
        bram[38] = 32'hfcdff06f;
        bram[39] = 32'h02099e63;
        bram[40] = 32'h05000513;
        bram[41] = 32'hf6dff0ef;
        bram[42] = 32'h04100513;
        bram[43] = 32'hf65ff0ef;
        bram[44] = 32'h05300513;
        bram[45] = 32'hf5dff0ef;
        bram[46] = 32'h05300513;
        bram[47] = 32'hf55ff0ef;
        bram[48] = 32'h00a00513;
        bram[49] = 32'hf4dff0ef;
        bram[50] = 32'h001f4337;
        bram[51] = 32'hfff30313;
        bram[52] = 32'hfe031ee3;
        bram[53] = 32'hf4dff06f;
        bram[54] = 32'h04600513;
        bram[55] = 32'hf35ff0ef;
        bram[56] = 32'h04100513;
        bram[57] = 32'hf2dff0ef;
        bram[58] = 32'h04900513;
        bram[59] = 32'hf25ff0ef;
        bram[60] = 32'h04c00513;
        bram[61] = 32'hf1dff0ef;
        bram[62] = 32'h00a00513;
        bram[63] = 32'hf15ff0ef;
        bram[64] = 32'h001f4337;
        bram[65] = 32'hfff30313;
        bram[66] = 32'hfe031ee3;
        bram[67] = 32'hf15ff06f;
    end

endmodule
