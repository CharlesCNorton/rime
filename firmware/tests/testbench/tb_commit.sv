// Testbench: SDRAM-to-flash commit loop (SDRAM_WRITE16, SDRAM_TO_FLASH, verify readback).
`timescale 1ns/1ps

module tb_commit;
    localparam integer CLK_HZ = 25000000;
    localparam integer CLK_NS = 40;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;
    reg rst = 1;

    reg serial_line = 1;
    wire rx_valid; wire [7:0] rx_data;
    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(115200)) RX (.clk(clk), .rx(serial_line), .finish(rx_valid), .data(rx_data));

    wire tx_send; wire [7:0] tx_data_out;

    wire [2:0] spi_op; wire [23:0] spi_addr; wire [127:0] spi_prog_data; wire spi_start_w;
    reg spi_busy = 0, spi_done = 0, spi_ok = 1;
    reg [127:0] spi_read_data = 0; reg [15:0] spi_status = 0; reg [23:0] spi_jedec = 24'hEF4018;

    wire sdram_start_w, sdram_wr_w; wire [23:0] sdram_base_addr; wire [127:0] sdram_wdata;
    reg [127:0] sdram_rdata = 0; reg sdram_done = 0, sdram_busy = 0;

    wire raw_req, raw_wr, raw_active; wire [23:0] raw_addr; wire [15:0] raw_wdata;
    wire busy_w; wire [4:0] gpio_led;

    rime_service #(.CLK_HZ(CLK_HZ)) DUT (
        .clk(clk), .rst(rst),
        .uart_rx_valid(rx_valid), .uart_rx_data(rx_data),
        .uart_tx_send(tx_send), .uart_tx_data(tx_data_out), .uart_tx_busy(1'b0),
        .spi_op(spi_op), .spi_addr(spi_addr), .spi_prog_data(spi_prog_data),
        .spi_start(spi_start_w), .spi_busy(spi_busy), .spi_done(spi_done),
        .spi_ok(spi_ok), .spi_read_data(spi_read_data),
        .spi_status(spi_status), .spi_jedec(spi_jedec),
        .sdram_start(sdram_start_w), .sdram_wr(sdram_wr_w),
        .sdram_base_addr(sdram_base_addr), .sdram_wdata(sdram_wdata),
        .sdram_rdata(sdram_rdata), .sdram_done(sdram_done), .sdram_busy(sdram_busy),
        .sdram_init_done(1'b1),
        .busy(busy_w), .gpio_led(gpio_led),
        .raw_req(raw_req), .raw_wr(raw_wr), .raw_addr(raw_addr), .raw_wdata(raw_wdata),
        .raw_rdata(16'd0), .raw_ready(1'b1), .raw_valid(1'b0), .raw_ack(1'b0), .raw_active(raw_active)
    );

    reg [2:0] sdram_delay = 0;
    always @(posedge clk) begin
        sdram_done <= 0;
        if (sdram_start_w) begin
            sdram_delay <= 4;
            sdram_busy <= 1;
            sdram_rdata <= {sdram_base_addr[7:0], 8'h01, sdram_base_addr[7:0], 8'h02,
                           sdram_base_addr[7:0], 8'h03, sdram_base_addr[7:0], 8'h04,
                           sdram_base_addr[7:0], 8'h05, sdram_base_addr[7:0], 8'h06,
                           sdram_base_addr[7:0], 8'h07, sdram_base_addr[7:0], 8'h08};
        end else if (sdram_delay > 0) begin
            sdram_delay <= sdram_delay - 1;
            if (sdram_delay == 1) begin sdram_done <= 1; sdram_busy <= 0; end
        end
    end

    reg [7:0] spi_delay = 0;
    reg [2:0] spi_op_reg = 0;
    always @(posedge clk) begin
        spi_done <= 0;
        if (spi_start_w) begin
            spi_op_reg <= spi_op;
            spi_busy <= 1;
            case (spi_op)
                3'd4: spi_delay <= 50;
                3'd5: spi_delay <= 20;
                3'd3: spi_delay <= 10;
                default: spi_delay <= 5;
            endcase
        end else if (spi_delay > 0) begin
            spi_delay <= spi_delay - 1;
            if (spi_delay == 1) begin
                spi_done <= 1; spi_ok <= 1; spi_busy <= 0;
                if (spi_op_reg == 3'd3) spi_read_data <= 128'hDEAD;
            end
        end
    end

    reg [3:0] prev_state = 0;
    always @(posedge clk) begin
        if (DUT.state != prev_state)
            $display("[%0t] state=%0d->%0d phase=%0d remaining=%0d flash=0x%06h sdram_w=0x%06h",
                $time, prev_state, DUT.state, DUT.loop_phase, DUT.loop_remaining,
                DUT.loop_flash_addr, DUT.loop_sdram_word);
        prev_state <= DUT.state;
        if (spi_start_w)
            $display("[%0t] SPI_START op=%0d addr=0x%06h", $time, spi_op, spi_addr);
        if (sdram_start_w)
            $display("[%0t] SDRAM_START addr=0x%06h wr=%0b", $time, sdram_base_addr, sdram_wr_w);
        if (tx_send)
            $display("[%0t] TX: 0x%02h", $time, tx_data_out);
    end

    localparam integer BIT_NS = 1000000000 / 115200;
    task uart_send(input [7:0] b);
    integer bit_idx;
    begin
        serial_line = 0; #(BIT_NS);
        for (bit_idx = 0; bit_idx < 8; bit_idx = bit_idx + 1) begin
            serial_line = b[bit_idx]; #(BIT_NS);
        end
        serial_line = 1; #(BIT_NS);
    end
    endtask

    initial begin
        $dumpfile("tb_commit.vcd");
        $dumpvars(0, tb_commit);
        rst = 1; #1000; rst = 0; #1000;

        $display("=== STREAM 64 bytes to SDRAM ===");
        uart_send(8'h84);
        uart_send(8'h00); uart_send(8'h00); uart_send(8'h00);
        uart_send(8'h00); uart_send(8'h40);
        begin : stream_data
            integer i;
            for (i = 0; i < 64; i = i + 1) uart_send(i[7:0]);
        end
        #(BIT_NS * 5);
        $display("Stream done. State=%0d", DUT.state);

        $display("");
        $display("=== SDRAM_TO_FLASH 64 bytes -> 0x300000 ===");
        uart_send(8'h83);
        uart_send(8'h30); uart_send(8'h00); uart_send(8'h00);
        uart_send(8'h00); uart_send(8'h00); uart_send(8'h40);

        #50000000;
        $display("Final state=%0d remaining=%0d", DUT.state, DUT.loop_remaining);
        $finish;
    end
endmodule
