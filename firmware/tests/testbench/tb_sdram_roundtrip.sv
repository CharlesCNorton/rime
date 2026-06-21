// Simulation testbench: SDRAM controller round-trip via behavioral model.
// Writes 8 words, reads them back, checks match.
//
// Run: iverilog -g2012 -o tb firmware/tests/testbench/tb_sdram_roundtrip.sv \
//        firmware/core/sdram_controller.sv firmware/tests/testbench/sdram_model.sv \
//      && vvp tb

`timescale 1ns / 1ps

module tb_sdram_roundtrip;
    reg clk = 0;
    always #20 clk = ~clk;  // 25 MHz

    reg rst = 1;
    reg req = 0, wr = 0;
    reg [23:0] addr = 0;
    reg [15:0] wdata = 0;
    wire [15:0] rdata;
    wire ready, valid, ack, init_done;

    wire        sdram_clk, sdram_cke, sdram_csn;
    wire        sdram_rasn, sdram_casn, sdram_wen;
    wire [1:0]  sdram_ba, sdram_dqm;
    wire [12:0] sdram_a;
    wire [15:0] sdram_dq;
    wire [15:0] sdram_dq_out;
    wire        sdram_dq_oe;

    assign sdram_dq = sdram_dq_oe ? sdram_dq_out : 16'bz;

    sdram_controller #(.CLK_HZ(25000000)) DUT (
        .clk(clk), .rst(rst),
        .req(req), .wr(wr), .addr(addr), .wdata(wdata),
        .rdata(rdata), .ready(ready), .valid(valid), .ack(ack),
        .init_done(init_done),
        .sdram_clk(sdram_clk), .sdram_cke(sdram_cke),
        .sdram_csn(sdram_csn), .sdram_rasn(sdram_rasn),
        .sdram_casn(sdram_casn), .sdram_wen(sdram_wen),
        .sdram_ba(sdram_ba), .sdram_a(sdram_a),
        .sdram_dq_out(sdram_dq_out), .sdram_dq_in(sdram_dq),
        .sdram_dq_oe(sdram_dq_oe), .sdram_dqm(sdram_dqm),
        .dbg_last_write_a(), .dbg_last_write_ba(), .dbg_last_req_addr()
    );

    sdram_model MODEL (
        .clk(sdram_clk), .cke(sdram_cke), .csn(sdram_csn),
        .rasn(sdram_rasn), .casn(sdram_casn), .wen(sdram_wen),
        .ba(sdram_ba), .a(sdram_a), .dq(sdram_dq), .dqm(sdram_dqm)
    );

    integer i;
    integer pass_count = 0;
    integer fail_count = 0;
    reg [15:0] expected [0:7];

    task write_word(input [23:0] a, input [15:0] d);
        begin
            @(posedge clk);
            while (!ready) @(posedge clk);
            addr <= a; wdata <= d; wr <= 1; req <= 1;
            @(posedge clk);
            while (!ack) @(posedge clk);
            req <= 0; wr <= 0;
            while (!ready) @(posedge clk);
        end
    endtask

    task read_word(input [23:0] a, output [15:0] d);
        begin
            @(posedge clk);
            while (!ready) @(posedge clk);
            addr <= a; wr <= 0; req <= 1;
            @(posedge clk);
            while (!ack) @(posedge clk);
            req <= 0;
            while (!valid) @(posedge clk);
            d = rdata;
        end
    endtask

    reg [15:0] read_val;
    initial begin
        #200 rst = 0;

        // Wait for SDRAM init
        while (!init_done) @(posedge clk);
        $display("SDRAM init done at %0t", $time);

        // Write 8 words to bank 0, row 0
        for (i = 0; i < 8; i = i + 1) begin
            expected[i] = 16'hA500 + i;
            write_word(i[23:0], expected[i]);
        end
        $display("Wrote 8 words");

        // Read them back
        for (i = 0; i < 8; i = i + 1) begin
            read_word(i[23:0], read_val);
            if (read_val === expected[i]) begin
                pass_count = pass_count + 1;
            end else begin
                $display("FAIL: addr=%0d expected=%04h got=%04h", i, expected[i], read_val);
                fail_count = fail_count + 1;
            end
        end

        // Write to a different row (addr 0x200 = row 1, col 0)
        write_word(24'h000200, 16'hBEEF);
        read_word(24'h000200, read_val);
        if (read_val === 16'hBEEF) pass_count = pass_count + 1;
        else begin $display("FAIL: row1 col0"); fail_count = fail_count + 1; end

        // Verify row 0 data survived the row switch
        read_word(24'h000000, read_val);
        if (read_val === 16'hA500) pass_count = pass_count + 1;
        else begin $display("FAIL: row0 after switch got=%04h", read_val); fail_count = fail_count + 1; end

        $display("");
        $display("SDRAM round-trip: %0d passed, %0d failed", pass_count, fail_count);
        if (fail_count == 0) $display("PASS");
        else $display("FAIL");
        $finish;
    end

    // Timeout
    initial begin
        #10000000;
        $display("TIMEOUT");
        $finish;
    end
endmodule
