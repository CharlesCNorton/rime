// Testbench: SDRAM streaming debug (SDRAM_WRITE_STREAM timeout and recovery).
`timescale 1ns/1ps

module tb_stream_debug;
    localparam integer CLK_HZ = 25000000;
    localparam integer CLK_NS = 40;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;

    reg rst = 1;

    reg        rx_valid = 0;
    reg  [7:0] rx_data = 0;
    wire       tx_send;
    wire [7:0] tx_data;
    reg        tx_busy = 0;

    wire [2:0]  spi_op;
    wire [23:0] spi_addr;
    wire [127:0] spi_prog_data;
    wire        spi_start;
    reg         spi_busy = 0;
    reg         spi_done = 0;
    reg         spi_ok = 1;
    reg  [127:0] spi_read_data = 0;
    reg  [15:0] spi_status = 0;
    reg  [23:0] spi_jedec = 24'hEF4018;

    wire        sdram_start_w;
    wire        sdram_wr_w;
    wire [23:0] sdram_base_addr;
    wire [127:0] sdram_wdata;
    reg  [127:0] sdram_rdata = 0;
    reg         sdram_done = 0;
    reg         sdram_busy = 0;
    reg         sdram_init_done = 1;

    wire raw_req, raw_wr, raw_active;
    wire [23:0] raw_addr;
    wire [15:0] raw_wdata;
    reg  [15:0] raw_rdata = 0;
    reg         raw_ready = 1;
    reg         raw_valid = 0;
    reg         raw_ack = 0;

    wire busy_w;
    wire [4:0] gpio_led;

    rime_service #(.CLK_HZ(CLK_HZ)) DUT (
        .clk(clk), .rst(rst),
        .uart_rx_valid(rx_valid), .uart_rx_data(rx_data),
        .uart_tx_send(tx_send), .uart_tx_data(tx_data), .uart_tx_busy(tx_busy),
        .spi_op(spi_op), .spi_addr(spi_addr), .spi_prog_data(spi_prog_data),
        .spi_start(spi_start), .spi_busy(spi_busy), .spi_done(spi_done),
        .spi_ok(spi_ok), .spi_read_data(spi_read_data),
        .spi_status(spi_status), .spi_jedec(spi_jedec),
        .sdram_start(sdram_start_w), .sdram_wr(sdram_wr_w),
        .sdram_base_addr(sdram_base_addr), .sdram_wdata(sdram_wdata),
        .sdram_rdata(sdram_rdata), .sdram_done(sdram_done),
        .sdram_busy(sdram_busy), .sdram_init_done(sdram_init_done),
        .busy(busy_w), .gpio_led(gpio_led),
        .raw_req(raw_req), .raw_wr(raw_wr), .raw_addr(raw_addr),
        .raw_wdata(raw_wdata), .raw_rdata(raw_rdata),
        .raw_ready(raw_ready), .raw_valid(raw_valid), .raw_ack(raw_ack),
        .raw_active(raw_active)
    );

    reg [2:0] sdram_delay = 0;
    always @(posedge clk) begin
        sdram_done <= 0;
        if (sdram_start_w) begin
            sdram_delay <= 4;
            sdram_busy <= 1;
        end else if (sdram_delay > 0) begin
            sdram_delay <= sdram_delay - 1;
            if (sdram_delay == 1) begin
                sdram_done <= 1;
                sdram_busy <= 0;
            end
        end
    end

    reg [7:0] tx_capture [0:63];
    integer tx_count = 0;
    always @(posedge clk) begin
        if (tx_send) begin
            tx_capture[tx_count] = tx_data;
            tx_count = tx_count + 1;
        end
    end

    task send_byte(input [7:0] b);
    begin
        @(posedge clk);
        rx_data = b;
        rx_valid = 1;
        @(posedge clk);
        rx_valid = 0;
        repeat (5) @(posedge clk);
    end
    endtask

    task monitor(input integer cycles);
    integer i;
    begin
        for (i = 0; i < cycles; i = i + 1) begin
            @(posedge clk);
            if (i < 50 || i % 1000 == 0 || DUT.state != DUT.state) begin
                $display("  cycle=%0d state=%0d rx_wr=%0d rx_rd=%0d rx_got=%0d/%0d byte_idx=%0d remaining=%0d idle_cnt=%0d wdog=%0d wdog_exp=%0b tx_count=%0d",
                    i, DUT.state, DUT.rx_wr, DUT.rx_rd, DUT.rx_got, DUT.rx_need,
                    DUT.stream_byte_idx, DUT.stream_remaining,
                    DUT.stream_idle_cnt, DUT.sdram_stream_wdog,
                    DUT.sdram_stream_wdog_expired, tx_count);
            end
        end
    end
    endtask

    integer i;
    initial begin
        $dumpfile("tb_stream_debug.vcd");
        $dumpvars(0, tb_stream_debug);

        rst = 1;
        repeat (20) @(posedge clk);
        rst = 0;
        repeat (10) @(posedge clk);

        $display("=== VERSION ===");
        tx_count = 0;
        send_byte(8'h00);
        repeat (50) @(posedge clk);
        $display("  TX count: %0d", tx_count);
        if (tx_count >= 3)
            $display("  Response: %02h %02h %02h", tx_capture[0], tx_capture[1], tx_capture[2]);

        $display("=== PING ===");
        tx_count = 0;
        send_byte(8'h01);
        repeat (50) @(posedge clk);
        $display("  TX count: %0d", tx_count);
        if (tx_count >= 2)
            $display("  Response: %02h %02h", tx_capture[0], tx_capture[1]);

        $display("=== WRITE_STREAM (16 bytes @ 0x280000) ===");
        tx_count = 0;

        $display("  Sending CMD 0x84...");
        send_byte(8'h84);
        $display("  state=%0d after cmd byte", DUT.state);

        $display("  Sending 5 param bytes...");
        send_byte(8'h28);
        send_byte(8'h00);
        send_byte(8'h00);
        send_byte(8'h00);
        send_byte(8'h10);
        $display("  state=%0d rx_got=%0d/%0d after params", DUT.state, DUT.rx_got, DUT.rx_need);
        repeat (10) @(posedge clk);
        $display("  state=%0d after settle (should be 7=S_SDRAM_STREAM)", DUT.state);
        $display("  stream_remaining=%0d stream_byte_idx=%0d", DUT.stream_remaining, DUT.stream_byte_idx);
        $display("  stream_idle_cnt=%0d", DUT.stream_idle_cnt);

        $display("  Sending 16 data bytes...");
        for (i = 0; i < 16; i = i + 1) begin
            send_byte(i[7:0]);
        end
        $display("  state=%0d after 16 data bytes", DUT.state);
        $display("  stream_remaining=%0d stream_byte_idx=%0d", DUT.stream_remaining, DUT.stream_byte_idx);
        $display("  sdram_start=%0b sdram_done=%0b sdram_busy=%0b", sdram_start_w, sdram_done, sdram_busy);

        $display("  Monitoring 200 cycles...");
        monitor(200);

        $display("  Final state=%0d remaining=%0d byte_idx=%0d idle_cnt=%0d",
            DUT.state, DUT.stream_remaining, DUT.stream_byte_idx, DUT.stream_idle_cnt);
        $display("  TX count: %0d", tx_count);
        if (tx_count >= 2)
            $display("  Response: %02h %02h", tx_capture[0], tx_capture[1]);

        $display("=== POST-STREAM PING ===");
        tx_count = 0;
        send_byte(8'h01);
        repeat (50) @(posedge clk);
        $display("  TX count: %0d  state=%0d", tx_count, DUT.state);
        if (tx_count >= 2)
            $display("  Response: %02h %02h", tx_capture[0], tx_capture[1]);

        $display("=== DONE ===");
        $finish;
    end

endmodule
