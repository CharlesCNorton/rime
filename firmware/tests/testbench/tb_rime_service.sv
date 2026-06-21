// Testbench: rime_service FSM (command dispatch, response framing, error handling).
`timescale 1ns/1ps

// Replaces the deleted tb_flash_service.sv.  Tests the core RIME
// protocol commands in service mode: VERSION, INFO, JEDEC, STATUS,
// PING, LAST_ERROR, STATS, CLEAR_ERROR, unknown-command error.
// Uses behavioural SPI and SDRAM responders wired to rime_service.

module tb_rime_service;
    localparam integer CLK_HZ  = 25000000;
    localparam integer CLK_NS  = 40;
    localparam integer BAUD    = 115200;
    localparam integer BIT_NS  = 1000000000 / BAUD;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;
    reg rst = 1;

    // ---- UART ----
    reg serial_line = 1;
    wire       rx_valid;
    wire [7:0] rx_data;
    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) RX (
        .clk(clk), .rx(serial_line), .finish(rx_valid), .data(rx_data)
    );
    wire       tx_send;
    wire [7:0] tx_data_out;

    // ---- SPI (behavioural) ----
    wire [2:0]   spi_op;
    wire [23:0]  spi_addr;
    wire [127:0] spi_prog_data;
    wire         spi_start_w;
    reg          spi_busy = 0;
    reg          spi_done = 0;
    reg          spi_ok   = 1;
    reg  [127:0] spi_read_data = 128'hA5A5_CAFE_BABE_DEAD_BEEF_1234_5678_9ABC;
    reg  [15:0]  spi_status = 16'h0002;
    reg  [23:0]  spi_jedec  = 24'hEF4018;

    reg [7:0] spi_delay = 0;
    always @(posedge clk) begin
        spi_done <= 0;
        if (spi_start_w) begin
            spi_busy  <= 1;
            spi_delay <= 5;
        end else if (spi_delay > 0) begin
            spi_delay <= spi_delay - 1;
            if (spi_delay == 1) begin
                spi_done <= 1;
                spi_ok   <= 1;
                spi_busy <= 0;
            end
        end
    end

    // ---- SDRAM (stub) ----
    wire         sdram_start_w, sdram_wr_w;
    wire [23:0]  sdram_base_addr;
    wire [127:0] sdram_wdata;
    reg  [127:0] sdram_rdata = 0;
    reg          sdram_done  = 0;
    reg          sdram_busy  = 0;

    // ---- Raw SDRAM (stub) ----
    wire raw_req, raw_wr, raw_active;
    wire [23:0] raw_addr;
    wire [15:0] raw_wdata;

    // ---- SD (stub) ----
    wire        sd_start;
    wire [2:0]  sd_op;
    wire [31:0] sd_lba;
    wire [4:0]  sd_chunk_idx;
    wire [8:0]  sd_write_addr_w;
    wire [8:0]  sd_load_addr_w;
    wire [7:0]  sd_load_data_w;
    wire        sd_load_en_w;
    wire        sd_det_in_w;
    wire        reset_request_w;

    // ---- Outputs ----
    wire        busy_w;
    wire [4:0]  gpio_led;

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
        .sdram_rdata(sdram_rdata), .sdram_done(sdram_done),
        .sdram_busy(sdram_busy), .sdram_init_done(1'b1),
        .busy(busy_w), .gpio_led(gpio_led),
        .raw_req(raw_req), .raw_wr(raw_wr), .raw_addr(raw_addr),
        .raw_wdata(raw_wdata), .raw_rdata(16'd0),
        .raw_ready(1'b1), .raw_valid(1'b0), .raw_ack(1'b0),
        .raw_active(raw_active),
        .sd_start(sd_start), .sd_op(sd_op), .sd_lba(sd_lba),
        .sd_chunk_idx(sd_chunk_idx),
        .sd_busy(1'b0), .sd_done(1'b0), .sd_ok(1'b0),
        .sd_card_present(1'b0), .sd_initialized(1'b0), .sd_high_capacity(1'b0),
        .sd_last_error(8'd0), .sd_last_r1(8'd0),
        .sd_read_data(128'd0), .sd_read_crc32(32'd0),
        .sd_write_addr(sd_write_addr_w), .sd_write_data(8'd0),
        .sd_load_addr(sd_load_addr_w), .sd_load_data(sd_load_data_w),
        .sd_load_en(sd_load_en_w), .sd_det_in(sd_det_in_w),
        .reset_request(reset_request_w),
        .sd_dbg_state(5'd0), .sd_dbg_shift_in(8'd0), .sd_dbg_shift_busy(1'b0)
    );

    // ---- UART bit-bang task ----
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

    // ---- Response capture ----
    reg [7:0] captured [0:31];
    integer capture_idx;

    task drain(input integer max_bytes, input integer timeout_ns);
    integer waited;
    begin
        capture_idx = 0;
        waited = 0;
        while (capture_idx < max_bytes && waited < timeout_ns) begin
            @(posedge clk);
            waited = waited + CLK_NS;
            if (tx_send) begin
                captured[capture_idx] = tx_data_out;
                capture_idx = capture_idx + 1;
            end
        end
    end
    endtask

    // ---- Test infrastructure ----
    integer errors = 0;

    task check(input [255:0] name, input ok);
    begin
        if (ok)
            $display("  [PASS] %0s", name);
        else begin
            $display("  [FAIL] %0s", name);
            errors = errors + 1;
        end
    end
    endtask

    // ---- Tests ----
    initial begin
        $dumpfile("tb_rime_service.vcd");
        $dumpvars(0, tb_rime_service);

        rst = 1;
        #1000;
        rst = 0;
        #(BIT_NS * 2);

        // ================================================
        // Board starts in app mode (phase 4).  Enter service.
        // ================================================
        $display("--- Enter service mode ---");
        uart_send(8'h02);                          // CMD_ENTER_SERVICE
        drain(2, BIT_NS * 50);
        check("ENTER_SERVICE ack", capture_idx >= 2 && captured[0] == 8'h02 && captured[1] == 8'hAC);
        #(BIT_NS * 3);

        // ================================================
        // VERSION in service mode -> phase 5
        // ================================================
        $display("--- Service commands ---");
        uart_send(8'h00);                          // CMD_HELLO
        drain(3, BIT_NS * 20);
        check("VERSION cmd echo",   capture_idx >= 3 && captured[0] == 8'h00);
        check("VERSION phase == 5", captured[1] == 8'd5);
        #(BIT_NS * 2);

        // ================================================
        // PING
        // ================================================
        uart_send(8'h01);                          // CMD_PING
        drain(2, BIT_NS * 20);
        check("PING ack", capture_idx >= 2 && captured[0] == 8'h01 && captured[1] == 8'hAC);
        #(BIT_NS * 2);

        // ================================================
        // INFO
        // ================================================
        uart_send(8'h73);                          // CMD_INFO
        drain(10, BIT_NS * 20);
        check("INFO length",     capture_idx >= 10);
        check("INFO cmd echo",   captured[0] == 8'h73);
        check("INFO phase == 5", captured[1] == 8'd5);
        check("INFO version > 0", captured[2] > 0);
        check("INFO max_prog == 16", captured[5] == 8'd16);
        check("INFO read_chunk == 16", captured[6] == 8'd16);
        #(BIT_NS * 2);

        // ================================================
        // JEDEC (exercises SPI behavioural model)
        // ================================================
        uart_send(8'h74);                          // CMD_JEDEC
        drain(4, BIT_NS * 200);
        check("JEDEC length",    capture_idx >= 4);
        check("JEDEC cmd echo",  captured[0] == 8'h74);
        check("JEDEC mfr == EF", captured[1] == 8'hEF);
        check("JEDEC dev == 40", captured[2] == 8'h40);
        check("JEDEC cap == 18", captured[3] == 8'h18);
        #(BIT_NS * 2);

        // ================================================
        // STATUS
        // ================================================
        uart_send(8'h71);                          // CMD_STATUS
        drain(3, BIT_NS * 200);
        check("STATUS length",   capture_idx >= 3);
        check("STATUS cmd echo", captured[0] == 8'h71);
        check("STATUS sr1",      captured[1] == 8'h02);
        check("STATUS sr2",      captured[2] == 8'h00);
        #(BIT_NS * 2);

        // ================================================
        // STATS
        // ================================================
        uart_send(8'h77);                          // CMD_STATS
        drain(9, BIT_NS * 20);
        check("STATS length",   capture_idx >= 9);
        check("STATS cmd echo", captured[0] == 8'h77);
        check("STATS cmd_count > 0", {captured[1], captured[2]} > 0);
        #(BIT_NS * 2);

        // ================================================
        // LAST_ERROR (should be clear)
        // ================================================
        uart_send(8'h76);                          // CMD_LAST_ERROR
        drain(7, BIT_NS * 20);
        check("LAST_ERROR length",   capture_idx >= 7);
        check("LAST_ERROR cmd echo", captured[0] == 8'h76);
        #(BIT_NS * 2);

        // ================================================
        // Unknown command -> error frame (0xFF, 0x01, cmd)
        // ================================================
        uart_send(8'hFE);                          // unknown
        drain(3, BIT_NS * 20);
        check("Unknown cmd error byte", capture_idx >= 3 && captured[0] == 8'hFF);
        check("Unknown cmd code == 01", captured[1] == 8'h01);
        check("Unknown cmd echo",       captured[2] == 8'hFE);
        #(BIT_NS * 2);

        // ================================================
        // CLEAR_ERROR
        // ================================================
        uart_send(8'h78);                          // CMD_CLEAR_ERROR
        drain(2, BIT_NS * 20);
        check("CLEAR_ERROR ack", capture_idx >= 2 && captured[0] == 8'h78 && captured[1] == 8'hAC);

        // Verify error is now clear
        uart_send(8'h76);                          // CMD_LAST_ERROR
        drain(7, BIT_NS * 20);
        check("LAST_ERROR now clear", capture_idx >= 7 && captured[6] == 8'h00);
        #(BIT_NS * 2);

        // ================================================
        // Summary
        // ================================================
        #(BIT_NS * 5);
        if (errors == 0)
            $display("PASS: rime_service protocol tests (%0d checks)", 0);
        else
            $display("FAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #(CLK_NS * 50000000);
        $display("TIMEOUT");
        $finish;
    end
endmodule
