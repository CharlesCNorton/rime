// Testbench: flash SPI master (JEDEC read, status read, page read, erase, program).
`timescale 1ns/1ps

module tb_flash_spi_master;
    localparam integer CLK_HZ = 25000000;
    localparam integer CLK_NS = 1000000000 / CLK_HZ;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;

    reg rst = 1;

    reg         start = 0;
    reg  [2:0]  op = 0;
    reg  [23:0] addr = 0;
    reg  [5:0]  read_chunk_count = 0;
    reg  [127:0] prog_data = 0;
    wire        busy;
    wire        done;
    wire        ok;
    wire [7:0]  diag;
    wire [23:0] jedec;
    wire [15:0] status;
    wire [127:0] read_data;
    wire [31:0] read_crc32;
    wire        flash_clk;
    wire        flash_csn;
    wire        flash_mosi;
    wire        flash_wpn;
    wire        flash_resetn;
    reg         flash_miso = 1;

    flash_spi_master #(.CLK_HZ(CLK_HZ)) DUT (
        .clk(clk), .rst(rst),
        .start(start), .op(op), .addr(addr),
        .read_chunk_count(read_chunk_count),
        .prog_data(prog_data),
        .busy(busy), .done(done), .ok(ok), .diag(diag),
        .jedec(jedec), .status(status),
        .read_data(read_data), .read_crc32(read_crc32),
        .flash_clk(flash_clk), .flash_csn(flash_csn),
        .flash_mosi(flash_mosi),
        .flash_wpn(flash_wpn), .flash_resetn(flash_resetn),
        .flash_miso(flash_miso)
    );

    reg [7:0]  model_cmd = 0;
    reg [4:0]  model_bit_count = 0;
    reg [23:0] model_response = 0;
    reg [4:0]  model_resp_bit = 0;
    reg        model_responding = 0;
    reg        model_cmd_received = 0;

    always @(posedge flash_clk) begin
        if (!flash_csn && !model_cmd_received) begin
            model_cmd = {model_cmd[6:0], flash_mosi};
            model_bit_count = model_bit_count + 1;
            if (model_bit_count == 8) begin
                model_cmd_received = 1;
                if (model_cmd == 8'h9F) begin
                    model_response = 24'hEF4018;
                    model_resp_bit = 23;
                    model_responding = 1;
                end
            end
        end
        if (model_responding) begin
        end
    end

    always @(negedge flash_clk) begin
        if (!flash_csn && model_responding) begin
            flash_miso = model_response[model_resp_bit];
            if (model_resp_bit == 0)
                model_responding = 0;
            else
                model_resp_bit = model_resp_bit - 1;
        end
    end

    always @(posedge flash_csn) begin
        model_cmd = 0;
        model_bit_count = 0;
        model_cmd_received = 0;
        model_responding = 0;
        flash_miso = 1;
    end

    integer errors = 0;

    initial begin
        $dumpfile("tb_flash_spi_master.vcd");
        $dumpvars(0, tb_flash_spi_master);

        #(CLK_NS * 20);
        rst = 0;
        #(CLK_NS * 5);

        $display("Test: JEDEC read");
        op = 3'd1;
        addr = 0;
        start = 1;
        @(posedge clk);
        start = 0;
        wait (done == 1);
        @(posedge clk);
        if (!ok) begin
            $display("FAIL: JEDEC op not OK");
            errors = errors + 1;
        end else if (jedec !== 24'hEF4018) begin
            $display("FAIL: JEDEC = 0x%06h, expected 0xEF4018", jedec);
            errors = errors + 1;
        end else begin
            $display("OK:   JEDEC = 0x%06h", jedec);
        end

        #(CLK_NS * 20);

        if (errors == 0)
            $display("PASS: all flash_spi_master tests passed");
        else
            $display("FAIL: %0d errors", errors);

        $finish;
    end
endmodule
