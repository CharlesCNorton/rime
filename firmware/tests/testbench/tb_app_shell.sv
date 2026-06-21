// Testbench: app shell round-trip (app mode, ENTER_SERVICE, EXIT_SERVICE, command gating).
`timescale 1ns/1ps

// Replaces the deleted tb_auto_recovery.sv.  Tests the app shell
// (phase 4) behaviour and the ENTER_SERVICE / EXIT_SERVICE round-trip.
//
// Coverage:
//   - After reset the board is in app mode (phase 4).
//   - App-mode VERSION returns phase 4.
//   - App-mode PING works.
//   - App-mode UPTIME returns a 4-byte seconds counter.
//   - App-mode IDENTITY returns "RIME" + versions + app_mode flag.
//   - Service commands (e.g. INFO) are rejected in app mode.
//   - ENTER_SERVICE transitions to phase 5.
//   - Service-mode VERSION confirms phase 5.
//   - EXIT_SERVICE returns to phase 4.
//   - Post-exit VERSION confirms phase 4.
//   - Second ENTER_SERVICE works (repeated round-trip).

module tb_app_shell;
    localparam integer CLK_HZ = 25000000;
    localparam integer CLK_NS = 40;
    localparam integer BAUD   = 115200;
    localparam integer BIT_NS = 1000000000 / BAUD;

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

    // ---- SPI (tied off) ----
    wire [2:0]   spi_op;
    wire [23:0]  spi_addr;
    wire [127:0] spi_prog_data;
    wire         spi_start_w;

    // ---- SDRAM (tied off) ----
    wire         sdram_start_w, sdram_wr_w;
    wire [23:0]  sdram_base_addr;
    wire [127:0] sdram_wdata;

    // ---- Raw SDRAM (tied off) ----
    wire raw_req, raw_wr, raw_active;
    wire [23:0] raw_addr;
    wire [15:0] raw_wdata;

    // ---- SD (tied off) ----
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

    wire        busy_w;
    wire [4:0]  gpio_led;

    rime_service #(.CLK_HZ(CLK_HZ)) DUT (
        .clk(clk), .rst(rst),
        .uart_rx_valid(rx_valid), .uart_rx_data(rx_data),
        .uart_tx_send(tx_send), .uart_tx_data(tx_data_out), .uart_tx_busy(1'b0),
        .spi_op(spi_op), .spi_addr(spi_addr), .spi_prog_data(spi_prog_data),
        .spi_start(spi_start_w), .spi_busy(1'b0), .spi_done(1'b0),
        .spi_ok(1'b1), .spi_read_data(128'd0),
        .spi_status(16'd0), .spi_jedec(24'hEF4018),
        .sdram_start(sdram_start_w), .sdram_wr(sdram_wr_w),
        .sdram_base_addr(sdram_base_addr), .sdram_wdata(sdram_wdata),
        .sdram_rdata(128'd0), .sdram_done(1'b0),
        .sdram_busy(1'b0), .sdram_init_done(1'b1),
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

    // ---- UART bit-bang ----
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

    initial begin
        $dumpfile("tb_app_shell.vcd");
        $dumpvars(0, tb_app_shell);

        rst = 1;
        #1000;
        rst = 0;
        #(BIT_NS * 2);

        // ================================================
        // Phase 1: App mode after reset
        // ================================================
        $display("--- App mode (phase 4) ---");

        // VERSION -> phase 4
        uart_send(8'h00);
        drain(3, BIT_NS * 20);
        check("App VERSION length",     capture_idx >= 3);
        check("App VERSION echo",       captured[0] == 8'h00);
        check("App VERSION phase == 4", captured[1] == 8'd4);
        #(BIT_NS * 2);

        // PING
        uart_send(8'h01);
        drain(2, BIT_NS * 20);
        check("App PING ack", capture_idx >= 2 && captured[0] == 8'h01 && captured[1] == 8'hAC);
        #(BIT_NS * 2);

        // UPTIME (0x05) -> 5 bytes: cmd + 4-byte seconds
        uart_send(8'h05);
        drain(5, BIT_NS * 20);
        check("App UPTIME length",   capture_idx >= 5);
        check("App UPTIME cmd echo", captured[0] == 8'h05);
        #(BIT_NS * 2);

        // IDENTITY (0x06) -> 10 bytes: cmd + "RIME" + app_ver + svc_ver + mode
        uart_send(8'h06);
        drain(10, BIT_NS * 20);
        check("App IDENTITY length",   capture_idx >= 10);
        check("App IDENTITY cmd echo", captured[0] == 8'h06);
        check("App IDENTITY 'R'",      captured[1] == 8'h52);
        check("App IDENTITY 'I'",      captured[2] == 8'h49);
        check("App IDENTITY 'M'",      captured[3] == 8'h4D);
        check("App IDENTITY 'E'",      captured[4] == 8'h45);
        check("App IDENTITY app_mode == 1", captured[9] == 8'h01);
        #(BIT_NS * 2);

        // INFO should be REJECTED in app mode (error frame)
        uart_send(8'h73);
        drain(3, BIT_NS * 20);
        check("App INFO rejected",          capture_idx >= 3);
        check("App INFO error byte == 0xFF", captured[0] == 8'hFF);
        check("App INFO error code == 0x01", captured[1] == 8'h01);
        #(BIT_NS * 2);

        // ================================================
        // Phase 2: Enter service mode
        // ================================================
        $display("--- ENTER_SERVICE ---");
        uart_send(8'h02);
        drain(2, BIT_NS * 50);
        check("ENTER_SERVICE ack", capture_idx >= 2 && captured[0] == 8'h02 && captured[1] == 8'hAC);
        #(BIT_NS * 3);

        // VERSION -> phase 5
        uart_send(8'h00);
        drain(3, BIT_NS * 20);
        check("Svc VERSION phase == 5", capture_idx >= 3 && captured[1] == 8'd5);
        #(BIT_NS * 2);

        // IDENTITY with app_mode == 0
        uart_send(8'h06);
        drain(10, BIT_NS * 20);
        check("Svc IDENTITY app_mode == 0", capture_idx >= 10 && captured[9] == 8'h00);
        #(BIT_NS * 2);

        // INFO now works
        uart_send(8'h73);
        drain(10, BIT_NS * 20);
        check("Svc INFO responds",    capture_idx >= 10);
        check("Svc INFO phase == 5",  captured[1] == 8'd5);
        #(BIT_NS * 2);

        // ================================================
        // Phase 3: EXIT_SERVICE round-trip
        // ================================================
        $display("--- EXIT_SERVICE ---");
        uart_send(8'h04);
        drain(2, BIT_NS * 20);
        check("EXIT_SERVICE ack", capture_idx >= 2 && captured[0] == 8'h04 && captured[1] == 8'hAC);
        #(BIT_NS * 2);

        // VERSION -> phase 4 again
        uart_send(8'h00);
        drain(3, BIT_NS * 20);
        check("Post-exit VERSION phase == 4", capture_idx >= 3 && captured[1] == 8'd4);
        #(BIT_NS * 2);

        // PING still works
        uart_send(8'h01);
        drain(2, BIT_NS * 20);
        check("Post-exit PING", capture_idx >= 2 && captured[0] == 8'h01 && captured[1] == 8'hAC);
        #(BIT_NS * 2);

        // ================================================
        // Phase 4: Second round-trip (re-enter, re-exit)
        // ================================================
        $display("--- Second round-trip ---");
        uart_send(8'h02);
        drain(2, BIT_NS * 50);
        check("Re-enter ack", capture_idx >= 2 && captured[0] == 8'h02 && captured[1] == 8'hAC);
        #(BIT_NS * 3);

        uart_send(8'h00);
        drain(3, BIT_NS * 20);
        check("Re-enter phase == 5", capture_idx >= 3 && captured[1] == 8'd5);
        #(BIT_NS * 2);

        uart_send(8'h04);
        drain(2, BIT_NS * 20);
        check("Re-exit ack", capture_idx >= 2 && captured[0] == 8'h04 && captured[1] == 8'hAC);
        #(BIT_NS * 2);

        uart_send(8'h00);
        drain(3, BIT_NS * 20);
        check("Re-exit phase == 4", capture_idx >= 3 && captured[1] == 8'd4);
        #(BIT_NS * 2);

        // ================================================
        // Summary
        // ================================================
        #(BIT_NS * 5);
        if (errors == 0)
            $display("PASS: app shell and mode transition tests");
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
