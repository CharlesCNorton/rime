// Testbench: SPI stale-read regression (sequential reads must not return stale data).
`timescale 1ns/1ps

module tb_spi_stale;
    localparam integer CLK_HZ = 25000000;
    localparam integer CLK_NS = 40;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;
    reg rst = 1;

    reg         start = 0;
    reg  [2:0]  op = 0;
    reg  [23:0] addr = 0;
    reg  [5:0]  read_chunk_count = 1;
    reg  [127:0] prog_data = 0;
    wire        busy, done, ok;
    wire [7:0]  diag;
    wire [23:0] jedec_out;
    wire [15:0] status_out;
    wire [127:0] read_data;
    wire [31:0] read_crc32;
    wire        flash_clk_w, flash_csn_w, flash_mosi_w, flash_wpn_w, flash_resetn_w;
    wire        flash_miso_w;

    flash_spi_master #(.CLK_HZ(CLK_HZ), .SCK_HZ(12000000)) DUT (
        .clk(clk), .rst(rst),
        .start(start), .op(op), .addr(addr),
        .read_chunk_count(read_chunk_count), .prog_data(prog_data),
        .busy(busy), .done(done), .ok(ok), .diag(diag),
        .jedec(jedec_out), .status(status_out),
        .read_data(read_data), .read_crc32(read_crc32),
        .flash_clk(flash_clk_w), .flash_csn(flash_csn_w),
        .flash_mosi(flash_mosi_w), .flash_wpn(flash_wpn_w),
        .flash_resetn(flash_resetn_w), .flash_miso(flash_miso_w)
    );

    reg [7:0] flash_mem [0:255];
    reg [7:0] f_sr1 = 0;
    reg [7:0] f_cmd = 0;
    reg [4:0] f_bit_cnt = 0;
    reg       f_cmd_done = 0;
    reg [23:0] f_addr = 0;
    reg [1:0] f_addr_byte = 0;
    reg       f_addr_done = 0;
    reg       f_reading = 0;
    reg [7:0] f_read_idx = 0;
    reg [2:0] f_resp_bit = 7;
    reg [7:0] f_resp_byte = 0;
    reg       f_responding = 0;
    reg       f_wren = 0;
    reg       f_programming = 0;
    reg [7:0] f_prog_buf [0:15];
    reg [3:0] f_prog_cnt = 0;
    reg [23:0] f_prog_addr = 0;
    reg [15:0] f_wip_timer = 0;

    reg f_miso = 1;
    assign flash_miso_w = f_miso;

    integer fi;
    initial begin
        for (fi = 0; fi < 256; fi = fi + 1) flash_mem[fi] = 8'hFF;
    end

    always @(posedge clk) begin
        if (f_wip_timer > 0) begin
            f_wip_timer <= f_wip_timer - 1;
            if (f_wip_timer == 1) begin
                f_sr1[0] <= 0;
                if (f_programming) begin
                    for (fi = 0; fi < 16; fi = fi + 1)
                        flash_mem[(f_prog_addr + fi) & 8'hFF] <= f_prog_buf[fi];
                    f_programming <= 0;
                end
            end
        end
    end

    always @(posedge flash_clk_w) begin
        if (!flash_csn_w) begin
            if (!f_cmd_done) begin
                f_cmd <= {f_cmd[6:0], flash_mosi_w};
                f_bit_cnt <= f_bit_cnt + 1;
                if (f_bit_cnt == 7) begin
                    f_cmd_done <= 1;
                    f_addr_byte <= 0;
                    f_addr_done <= 0;
                    f_prog_cnt <= 0;
                    if ({f_cmd[6:0], flash_mosi_w} == 8'h06) begin
                        f_wren <= 1;
                        f_cmd_done <= 0; f_bit_cnt <= 0;
                    end
                    if ({f_cmd[6:0], flash_mosi_w} == 8'h05) begin
                        f_responding <= 1;
                        f_resp_byte <= f_sr1;
                        f_resp_bit <= 7;
                    end
                    if ({f_cmd[6:0], flash_mosi_w} == 8'h9F) begin
                        f_responding <= 1;
                        f_resp_byte <= 8'hEF;
                        f_resp_bit <= 7;
                        f_read_idx <= 0;
                    end
                end
            end else if (!f_addr_done && (f_cmd == 8'h03 || f_cmd == 8'h02 || f_cmd == 8'hD8)) begin
                f_addr <= {f_addr[15:0], flash_mosi_w};
                f_bit_cnt <= f_bit_cnt + 1;
                if (f_bit_cnt == 31) begin
                    f_addr_done <= 1;
                    if (f_cmd == 8'h03) begin
                        f_responding <= 1;
                        f_resp_byte <= flash_mem[{f_addr[15:0], flash_mosi_w} & 24'hFF];
                        f_resp_bit <= 7;
                        f_read_idx <= 1;
                    end
                    if (f_cmd == 8'hD8) begin
                        f_sr1[0] <= 1;
                        f_wip_timer <= 5000;
                        for (fi = 0; fi < 256; fi = fi + 1) flash_mem[fi] <= 8'hFF;
                        f_wren <= 0;
                    end
                    if (f_cmd == 8'h02) begin
                        f_prog_addr <= {f_addr[15:0], flash_mosi_w};
                    end
                end
            end else if (f_addr_done && f_cmd == 8'h02) begin
                f_prog_buf[f_prog_cnt] <= {f_prog_buf[f_prog_cnt][6:0], flash_mosi_w};
                f_bit_cnt <= f_bit_cnt + 1;
                if (f_bit_cnt[2:0] == 3'd7) f_prog_cnt <= f_prog_cnt + 1;
            end
        end
    end

    always @(negedge flash_clk_w) begin
        if (!flash_csn_w && f_responding) begin
            f_miso <= f_resp_byte[f_resp_bit];
            if (f_resp_bit == 0) begin
                f_resp_bit <= 7;
                if (f_cmd == 8'h9F) begin
                    case (f_read_idx)
                        0: f_resp_byte <= 8'h40;
                        1: f_resp_byte <= 8'h18;
                        default: f_resp_byte <= 8'h00;
                    endcase
                    f_read_idx <= f_read_idx + 1;
                end else if (f_cmd == 8'h03) begin
                    f_resp_byte <= flash_mem[(f_prog_addr[7:0] + f_read_idx) & 8'hFF];
                    f_read_idx <= f_read_idx + 1;
                end else begin
                    f_responding <= 0;
                end
            end else begin
                f_resp_bit <= f_resp_bit - 1;
            end
        end else begin
            f_miso <= 1;
        end
    end

    always @(posedge flash_csn_w) begin
        f_cmd_done <= 0;
        f_bit_cnt <= 0;
        f_responding <= 0;
        f_reading <= 0;
        if (f_cmd == 8'h02 && f_wren) begin
            f_sr1[0] <= 1;
            f_wip_timer <= 500;
            f_programming <= 1;
            f_wren <= 0;
        end
    end

    task do_op(input [2:0] o, input [23:0] a, input [127:0] d);
    begin
        @(posedge clk);
        op <= o; addr <= a; prog_data <= d; start <= 1;
        @(posedge clk);
        start <= 0;
        wait (done == 1);
        @(posedge clk);
    end
    endtask

    integer i;
    reg [127:0] expected;
    initial begin
        $dumpfile("tb_spi_stale.vcd");
        $dumpvars(0, tb_spi_stale);
        rst = 1; #1000; rst = 0; #1000;

        do_op(3'd1, 24'd0, 128'd0);
        $display("JEDEC: %06h  ok=%b", jedec_out, ok);

        $display("Erasing...");
        do_op(3'd4, 24'h000000, 128'd0);
        $display("Erase done. ok=%b", ok);

        expected = {8'h00, 8'h01, 8'h02, 8'h03, 8'h04, 8'h05, 8'h06, 8'h07,
                    8'h08, 8'h09, 8'h0A, 8'h0B, 8'h0C, 8'h0D, 8'h0E, 8'h0F};
        $display("Programming 00-0F at addr 0...");
        do_op(3'd5, 24'h000000, expected);
        $display("Program done. ok=%b", ok);

        $display("Reading addr 0 (first read after program)...");
        do_op(3'd3, 24'h000000, 128'd0);
        $display("Read 0: %032h  ok=%b", read_data, ok);
        $display("Expect: %032h", expected);
        $display("Match:  %s", (read_data == expected) ? "YES" : "NO -- STALE");

        do_op(3'd3, 24'h000000, 128'd0);
        $display("Read 1: %032h  match=%s", read_data, (read_data == expected) ? "YES" : "NO");

        do_op(3'd3, 24'h000000, 128'd0);
        $display("Read 2: %032h  match=%s", read_data, (read_data == expected) ? "YES" : "NO");

        $display("=== DONE ===");
        $finish;
    end
endmodule
