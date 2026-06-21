// Testbench: UART-to-SDRAM streaming (SDRAM_WRITE_STREAM bulk transfer).
`timescale 1ns/1ps

module tb_stream_uart;
    localparam integer CLK_HZ = 25000000;
    localparam integer BAUD   = 115200;
    localparam integer CLK_NS = 40;
    localparam integer BIT_NS = 1000000000 / BAUD;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;

    reg rst = 1;

    reg serial_line = 1;

    wire       rx_valid;
    wire [7:0] rx_data;

    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) RX (
        .clk(clk), .rx(serial_line), .finish(rx_valid), .data(rx_data)
    );

    wire       tx_send;
    wire [7:0] tx_data_out;
    reg        tx_busy = 0;

    wire [2:0]  spi_op;
    wire [23:0] spi_addr;
    wire [127:0] spi_prog_data;
    wire        spi_start;

    wire        sdram_start_w;
    wire        sdram_wr_w;
    wire [23:0] sdram_base_addr;
    wire [127:0] sdram_wdata;
    reg  [127:0] sdram_rdata = 0;
    reg         sdram_done = 0;
    reg         sdram_busy = 0;

    wire raw_req, raw_wr, raw_active;
    wire [23:0] raw_addr;
    wire [15:0] raw_wdata;

    wire busy_w;
    wire [4:0] gpio_led;

    rime_service #(.CLK_HZ(CLK_HZ)) DUT (
        .clk(clk), .rst(rst),
        .uart_rx_valid(rx_valid), .uart_rx_data(rx_data),
        .uart_tx_send(tx_send), .uart_tx_data(tx_data_out), .uart_tx_busy(tx_busy),
        .spi_op(spi_op), .spi_addr(spi_addr), .spi_prog_data(spi_prog_data),
        .spi_start(spi_start), .spi_busy(1'b0), .spi_done(1'b0),
        .spi_ok(1'b1), .spi_read_data(128'd0),
        .spi_status(16'd0), .spi_jedec(24'hEF4018),
        .sdram_start(sdram_start_w), .sdram_wr(sdram_wr_w),
        .sdram_base_addr(sdram_base_addr), .sdram_wdata(sdram_wdata),
        .sdram_rdata(sdram_rdata), .sdram_done(sdram_done),
        .sdram_busy(sdram_busy), .sdram_init_done(1'b1),
        .busy(busy_w), .gpio_led(gpio_led),
        .raw_req(raw_req), .raw_wr(raw_wr), .raw_addr(raw_addr),
        .raw_wdata(raw_wdata), .raw_rdata(16'd0),
        .raw_ready(1'b1), .raw_valid(1'b0), .raw_ack(1'b0),
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
            if (tx_count < 64) tx_capture[tx_count] = tx_data_out;
            tx_count = tx_count + 1;
        end
    end

    task uart_send(input [7:0] b);
    integer bit_idx;
    begin
        serial_line = 0;
        #(BIT_NS);
        for (bit_idx = 0; bit_idx < 8; bit_idx = bit_idx + 1) begin
            serial_line = b[bit_idx];
            #(BIT_NS);
        end
        serial_line = 1;
        #(BIT_NS);
    end
    endtask

    function [79:0] state_name(input [3:0] s);
        case (s)
            4'd0: state_name = "IDLE     ";
            4'd1: state_name = "DISPATCH ";
            4'd2: state_name = "TX_RESP  ";
            4'd3: state_name = "RX_BYTES ";
            4'd4: state_name = "WAIT_SPI ";
            4'd5: state_name = "WAIT_SDRM";
            4'd6: state_name = "SD_FL_LP ";
            4'd7: state_name = "SD_STREAM";
            4'd8: state_name = "SD_VERIFY";
            default: state_name = "OTHER    ";
        endcase
    endfunction

    reg [3:0] prev_state = 0;
    reg       prev_rx_valid = 0;
    always @(posedge clk) begin
        if (DUT.state != prev_state) begin
            $display("  [%0t] STATE: %0d (%0s) -> %0d (%0s)  rx_got=%0d/%0d remaining=%0d byte_idx=%0d idle_cnt=%0d",
                $time, prev_state, state_name(prev_state), DUT.state, state_name(DUT.state),
                DUT.rx_got, DUT.rx_need, DUT.stream_remaining, DUT.stream_byte_idx,
                DUT.stream_idle_cnt);
        end
        if (rx_valid && !prev_rx_valid) begin
            $display("  [%0t] RX_BYTE: 0x%02h  state=%0d fifo_wr=%0d fifo_rd=%0d",
                $time, rx_data, DUT.state, DUT.rx_wr, DUT.rx_rd);
        end
        if (tx_send) begin
            $display("  [%0t] TX_BYTE: 0x%02h  state=%0d", $time, tx_data_out, DUT.state);
        end
        if (sdram_start_w) begin
            $display("  [%0t] SDRAM_START: addr=0x%06h wr=%0b", $time, sdram_base_addr, sdram_wr_w);
        end
        prev_state <= DUT.state;
        prev_rx_valid <= rx_valid;
    end

    integer i;
    initial begin
        $dumpfile("tb_stream_uart.vcd");
        $dumpvars(0, tb_stream_uart);

        rst = 1;
        #1000;
        rst = 0;
        #1000;

        $display("\n=== VERSION (real UART) ===");
        tx_count = 0;
        uart_send(8'h00);
        #(BIT_NS * 5);
        $display("  TX count: %0d", tx_count);
        if (tx_count >= 3)
            $display("  Response: 0x%02h 0x%02h 0x%02h", tx_capture[0], tx_capture[1], tx_capture[2]);

        $display("\n=== PING (real UART) ===");
        tx_count = 0;
        uart_send(8'h01);
        #(BIT_NS * 5);
        $display("  TX count: %0d", tx_count);

        $display("\n=== WRITE_STREAM 16 bytes @ 0x280000 (real UART) ===");
        tx_count = 0;

        uart_send(8'h84);
        uart_send(8'h28);
        uart_send(8'h00);
        uart_send(8'h00);
        uart_send(8'h00);
        uart_send(8'h10);
        for (i = 0; i < 16; i = i + 1) begin
            uart_send(i[7:0]);
        end

        $display("  All 22 bytes sent. Waiting...");
        #(BIT_NS * 20);

        $display("  state=%0d remaining=%0d byte_idx=%0d", DUT.state, DUT.stream_remaining, DUT.stream_byte_idx);
        $display("  TX count: %0d", tx_count);
        if (tx_count >= 2)
            $display("  Response: 0x%02h 0x%02h", tx_capture[0], tx_capture[1]);

        $display("\n=== POST-STREAM PING ===");
        tx_count = 0;
        uart_send(8'h01);
        #(BIT_NS * 5);
        $display("  TX count: %0d  state=%0d", tx_count, DUT.state);
        if (tx_count >= 2)
            $display("  Response: 0x%02h 0x%02h", tx_capture[0], tx_capture[1]);

        $display("\n=== WRITE_STREAM 0/16 bytes (timeout test) ===");
        tx_count = 0;
        uart_send(8'h84);
        uart_send(8'h28);
        uart_send(8'h00);
        uart_send(8'h00);
        uart_send(8'h00);
        uart_send(8'h10);
        $display("  Header sent. Waiting 700ms for timeout...");
        #700000000;
        $display("  state=%0d remaining=%0d idle_cnt=%0d wdog=%0d wdog_exp=%0b",
            DUT.state, DUT.stream_remaining, DUT.stream_idle_cnt,
            DUT.sdram_stream_wdog, DUT.sdram_stream_wdog_expired);
        $display("  TX count: %0d", tx_count);
        if (tx_count >= 1)
            $display("  Response: 0x%02h 0x%02h 0x%02h", tx_capture[0],
                tx_count > 1 ? tx_capture[1] : 8'hXX,
                tx_count > 2 ? tx_capture[2] : 8'hXX);

        $display("\n=== RECOVERY PING ===");
        tx_count = 0;
        uart_send(8'h01);
        #(BIT_NS * 5);
        $display("  TX count: %0d  state=%0d", tx_count, DUT.state);
        if (tx_count >= 2)
            $display("  Response: 0x%02h 0x%02h", tx_capture[0], tx_capture[1]);

        $display("\n=== SIMULATION COMPLETE ===");
        $finish;
    end

endmodule
