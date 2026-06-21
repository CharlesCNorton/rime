// Testbench: UART TX/RX loopback (transmit a byte, verify received byte matches).
`timescale 1ns/1ps

module tb_uart_loopback;
    localparam integer CLK_HZ   = 25000000;
    localparam integer BAUD     = 115200;
    localparam integer CLK_NS   = 1000000000 / CLK_HZ;
    localparam integer BIT_NS   = 1000000000 / BAUD;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;

    reg        tx_send = 0;
    reg  [7:0] tx_data = 0;
    wire       serial_line;

    wire       rx_finish;
    wire [7:0] rx_data;

    uart_tx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) TX (
        .clk(clk), .send(tx_send), .data(tx_data), .tx(serial_line)
    );

    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) RX (
        .clk(clk), .rx(serial_line), .finish(rx_finish), .data(rx_data)
    );

    integer errors = 0;
    integer i;
    reg [7:0] test_bytes [0:4];

    initial begin
        test_bytes[0] = 8'h00;
        test_bytes[1] = 8'hAC;
        test_bytes[2] = 8'hFF;
        test_bytes[3] = 8'h55;
        test_bytes[4] = 8'h7E;
    end

    task send_byte(input [7:0] b);
    begin
        @(posedge clk);
        tx_data = b;
        tx_send = 1;
        @(posedge clk);
        tx_send = 0;
        wait (rx_finish == 1);
        @(posedge clk);
        if (rx_data !== b) begin
            $display("FAIL: sent 0x%02h, received 0x%02h", b, rx_data);
            errors = errors + 1;
        end else begin
            $display("OK:   sent 0x%02h, received 0x%02h", b, rx_data);
        end
        #(BIT_NS * 2);
    end
    endtask

    initial begin
        $dumpfile("tb_uart_loopback.vcd");
        $dumpvars(0, tb_uart_loopback);

        #(CLK_NS * 10);

        for (i = 0; i < 5; i = i + 1) begin
            send_byte(test_bytes[i]);
        end

        if (errors == 0)
            $display("PASS: all %0d bytes looped back correctly", 5);
        else
            $display("FAIL: %0d errors", errors);

        $finish;
    end
endmodule
