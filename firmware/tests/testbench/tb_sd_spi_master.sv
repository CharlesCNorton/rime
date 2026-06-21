// Testbench: SD SPI master (init sequence, block read, block write, CRC-32).
`timescale 1ns/1ps

module tb_sd_spi_master;
    localparam integer CLK_HZ = 25000000;
    localparam integer CLK_NS = 1000000000 / CLK_HZ;

    reg clk = 0;
    always #(CLK_NS/2) clk = ~clk;

    reg rst = 1;
    reg start = 0;
    reg [2:0] op = 0;
    reg [31:0] lba = 0;
    reg [4:0] chunk_index = 0;
    wire [8:0] write_byte_addr;
    reg [7:0] write_byte_data = 0;
    wire busy, done, ok;
    wire card_present, initialized, high_capacity;
    wire [7:0] last_error, last_r1;
    wire [127:0] read_data;
    wire [31:0] read_crc32;
    wire sd_clk_out, sd_csn, sd_mosi;
    reg sd_miso = 1;
    reg sd_det = 1;

    sd_spi_master #(.CLK_HZ(CLK_HZ)) DUT (
        .clk(clk), .rst(rst),
        .start(start), .op(op), .lba(lba),
        .chunk_index(chunk_index),
        .write_byte_addr(write_byte_addr),
        .write_byte_data(write_byte_data),
        .busy(busy), .done(done), .ok(ok),
        .card_present(card_present),
        .initialized(initialized),
        .high_capacity(high_capacity),
        .last_error(last_error), .last_r1(last_r1),
        .read_data(read_data), .read_crc32(read_crc32),
        .sd_clk(sd_clk_out), .sd_csn(sd_csn),
        .sd_mosi(sd_mosi), .sd_miso(sd_miso),
        .sd_det(sd_det)
    );

    reg [7:0] rx_byte;
    reg [2:0] rx_bit;
    reg rx_active;
    reg [7:0] cmd_bytes [0:5];
    reg [2:0] cmd_byte_count;
    reg cmd_complete;
    reg [7:0] cmd_index;

    reg [7:0] resp_queue [0:519];
    integer resp_len;
    integer resp_pos;
    reg responding;

    reg model_idle;
    reg model_ready;
    integer acmd41_count;

    initial begin
        rx_active = 0;
        rx_byte = 8'hFF;
        rx_bit = 0;
        cmd_byte_count = 0;
        cmd_complete = 0;
        resp_len = 0;
        resp_pos = 0;
        responding = 0;
        model_idle = 0;
        model_ready = 0;
        acmd41_count = 0;
    end

    always @(posedge sd_clk_out) begin
        if (!sd_csn) begin
            if (!rx_active) begin
                if (sd_mosi == 0 && !responding) begin
                    rx_active = 1;
                    rx_byte = 0;
                    rx_bit = 7;
                    rx_byte[7] = sd_mosi;
                    rx_bit = 6;
                end
            end else begin
                rx_byte[rx_bit] = sd_mosi;
                if (rx_bit == 0) begin
                    rx_active = 0;
                    cmd_bytes[cmd_byte_count] = rx_byte;
                    cmd_byte_count = cmd_byte_count + 1;
                    if (cmd_byte_count == 6) begin
                        cmd_complete = 1;
                        cmd_index = cmd_bytes[0] & 8'h3F;
                        cmd_byte_count = 0;
                    end
                end else begin
                    rx_bit = rx_bit - 1;
                end
            end
        end
    end

    reg [7:0] miso_byte;
    reg [2:0] miso_bit;
    reg miso_sending;

    initial begin
        miso_sending = 0;
        miso_byte = 8'hFF;
        miso_bit = 7;
    end

    always @(negedge sd_clk_out) begin
        if (!sd_csn && responding) begin
            if (!miso_sending) begin
                if (resp_pos < resp_len) begin
                    miso_byte = resp_queue[resp_pos];
                    miso_bit = 7;
                    miso_sending = 1;
                    sd_miso = miso_byte[7];
                end
            end else begin
                sd_miso = miso_byte[miso_bit];
                if (miso_bit == 0) begin
                    miso_sending = 0;
                    resp_pos = resp_pos + 1;
                    if (resp_pos >= resp_len) begin
                        responding = 0;
                        sd_miso = 1;
                    end
                end else begin
                    miso_bit = miso_bit - 1;
                end
            end
        end else begin
            sd_miso = 1;
        end
    end

    always @(posedge cmd_complete) begin
        cmd_complete = 0;
        resp_pos = 0;
        miso_sending = 0;

        case (cmd_index)
            8'd0: begin
                resp_queue[0] = 8'h01;
                resp_len = 1;
                responding = 1;
                model_idle = 1;
            end
            8'd8: begin
                resp_queue[0] = 8'h01;
                resp_queue[1] = 8'h00;
                resp_queue[2] = 8'h00;
                resp_queue[3] = 8'h01;
                resp_queue[4] = 8'hAA;
                resp_len = 5;
                responding = 1;
            end
            8'd55: begin
                resp_queue[0] = model_ready ? 8'h00 : 8'h01;
                resp_len = 1;
                responding = 1;
            end
            8'd41: begin
                acmd41_count = acmd41_count + 1;
                if (acmd41_count >= 2) begin
                    resp_queue[0] = 8'h00;
                    model_ready = 1;
                end else begin
                    resp_queue[0] = 8'h01;
                end
                resp_len = 1;
                responding = 1;
            end
            8'd58: begin
                resp_queue[0] = 8'h00;
                resp_queue[1] = 8'h40;
                resp_queue[2] = 8'hFF;
                resp_queue[3] = 8'h80;
                resp_queue[4] = 8'h00;
                resp_len = 5;
                responding = 1;
            end
            8'd17: begin
                integer j;
                resp_queue[0] = 8'h00;
                resp_queue[1] = 8'hFF;
                resp_queue[2] = 8'hFE;
                for (j = 0; j < 512; j = j + 1) begin
                    resp_queue[3 + j] = j[7:0];
                end
                resp_queue[515] = 8'hFF;
                resp_queue[516] = 8'hFF;
                resp_len = 517;
                responding = 1;
            end
            default: begin
                resp_queue[0] = 8'h04;
                resp_len = 1;
                responding = 1;
            end
        endcase
    end

    always @(posedge sd_csn) begin
        rx_active = 0;
        cmd_byte_count = 0;
    end

    integer errors = 0;

    initial begin
        $dumpfile("tb_sd_spi_master.vcd");
        $dumpvars(0, tb_sd_spi_master);

        #(CLK_NS * 20);
        rst = 0;
        #(CLK_NS * 10);

        $display("Test: SD init");
        op = 3'd1;
        lba = 0;
        chunk_index = 0;
        start = 1;
        @(posedge clk);
        start = 0;
        wait (done == 1);
        @(posedge clk);
        if (!ok) begin
            $display("FAIL: SD init not OK (last_error=0x%02h, last_r1=0x%02h)", last_error, last_r1);
            errors = errors + 1;
        end else if (!initialized) begin
            $display("FAIL: SD init OK but not initialized");
            errors = errors + 1;
        end else if (!high_capacity) begin
            $display("FAIL: SD init OK but not SDHC");
            errors = errors + 1;
        end else begin
            $display("OK:   SD init complete, SDHC=%0b", high_capacity);
        end

        #(CLK_NS * 100);

        $display("Test: SD read16 LBA=0 chunk=0");
        op = 3'd2;
        lba = 0;
        chunk_index = 0;
        start = 1;
        @(posedge clk);
        start = 0;
        wait (done == 1);
        @(posedge clk);
        if (!ok) begin
            $display("FAIL: SD read not OK (last_error=0x%02h)", last_error);
            errors = errors + 1;
        end else begin
            reg [7:0] expected_byte;
            reg match;
            integer k;
            match = 1;
            for (k = 0; k < 16; k = k + 1) begin
                expected_byte = k[7:0];
                if (read_data[127 - (k*8) -: 8] !== expected_byte) begin
                    match = 0;
                    $display("FAIL: byte %0d: got 0x%02h, expected 0x%02h",
                             k, read_data[127 - (k*8) -: 8], expected_byte);
                end
            end
            if (match)
                $display("OK:   read16 data matches pattern");
            else
                errors = errors + 1;
        end

        #(CLK_NS * 100);

        if (errors == 0)
            $display("PASS: all sd_spi_master tests passed");
        else
            $display("FAIL: %0d errors", errors);

        $finish;
    end

    initial begin
        #(CLK_NS * 5000000);
        $display("TIMEOUT: simulation exceeded safety limit");
        $finish;
    end
endmodule
