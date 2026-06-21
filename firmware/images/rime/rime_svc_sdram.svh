// rime_svc_sdram.svh — SDRAM operation states extracted from rime_service.sv.
// `included inside the main FSM always_ff case block.
// States: S_WAIT_SDRAM, S_SDRAM_STREAM, S_SDRAM_FLASH_LOOP, S_SDRAM_VERIFY,
//         S_RAW_WAIT_ACK, S_RAW_WAIT_DONE, S_RAW_READ_DONE, S_RAW_READ_LOOP, S_RAW_READ_CAP

S_WAIT_SDRAM: begin
    if (sdram_done) begin
        if (cmd_reg == CMD_SDRAM_READ16) begin
            resp[0]  <= CMD_SDRAM_READ16;
            resp[1]  <= sdram_rdata_latch[127:120];
            resp[2]  <= sdram_rdata_latch[119:112];
            resp[3]  <= sdram_rdata_latch[111:104];
            resp[4]  <= sdram_rdata_latch[103:96];
            resp[5]  <= sdram_rdata_latch[95:88];
            resp[6]  <= sdram_rdata_latch[87:80];
            resp[7]  <= sdram_rdata_latch[79:72];
            resp[8]  <= sdram_rdata_latch[71:64];
            resp[9]  <= sdram_rdata_latch[63:56];
            resp[10] <= sdram_rdata_latch[55:48];
            resp[11] <= sdram_rdata_latch[47:40];
            resp[12] <= sdram_rdata_latch[39:32];
            resp[13] <= sdram_rdata_latch[31:24];
            resp[14] <= sdram_rdata_latch[23:16];
            resp[15] <= sdram_rdata_latch[15:8];
            resp[16] <= sdram_rdata_latch[7:0];
            resp_len <= 5'd17;
            resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
            state <= S_TX_RESP;
        end else begin
            resp[0] <= cmd_reg; resp[1] <= ACK;
            resp_len <= 5'd2;
            resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
            state <= S_TX_RESP;
        end
    end
end

S_RAW_READ_DONE: begin
    resp[0]  <= CMD_SDRAM_READ16;
    resp[1]  <= raw_rdata_buf[127:120];
    resp[2]  <= raw_rdata_buf[119:112];
    resp[3]  <= raw_rdata_buf[111:104];
    resp[4]  <= raw_rdata_buf[103:96];
    resp[5]  <= raw_rdata_buf[95:88];
    resp[6]  <= raw_rdata_buf[87:80];
    resp[7]  <= raw_rdata_buf[79:72];
    resp[8]  <= raw_rdata_buf[71:64];
    resp[9]  <= raw_rdata_buf[63:56];
    resp[10] <= raw_rdata_buf[55:48];
    resp[11] <= raw_rdata_buf[47:40];
    resp[12] <= raw_rdata_buf[39:32];
    resp[13] <= raw_rdata_buf[31:24];
    resp[14] <= raw_rdata_buf[23:16];
    resp[15] <= raw_rdata_buf[15:8];
    resp[16] <= raw_rdata_buf[7:0];
    resp_len <= 5'd17;
    resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
    state <= S_TX_RESP;
end

S_RAW_READ_LOOP: begin
    raw_req <= 1'b1;
    raw_wr <= 1'b0;
    if (raw_ack) begin
        raw_req <= 1'b0;
        state <= S_RAW_READ_CAP;
    end
end

S_RAW_READ_CAP: begin
    if (raw_valid) begin
        raw_rdata_buf[127 - (raw_word_idx * 16) -: 16] <= raw_rdata;
        if (raw_word_idx == 3'd7) begin
            raw_active <= 1'b0;
            state <= S_RAW_READ_DONE;
        end else begin
            raw_word_idx <= raw_word_idx + 3'd1;
            raw_addr <= raw_addr + 24'd1;
            raw_req <= 1'b1;
            state <= S_RAW_READ_LOOP;
        end
    end
end

S_SDRAM_STREAM: begin
    if (sdram_stream_wdog_expired) begin
        resp[0] <= 8'hFF; resp[1] <= 8'h04;
        resp[2] <= 8'd0; resp[3] <= {3'd0, state};
        resp[4] <= CMD_SDRAM_WRITE_STREAM; resp[5] <= 8'd0;
        resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
        resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
        last_err_code <= 8'h04; last_err_cmd <= CMD_SDRAM_WRITE_STREAM;
        last_err_detail <= 8'd0; last_err_valid <= 1'b1;
        err_count <= err_count + 16'd1;
        state <= S_TX_RESP;
    end else if (stream_byte_idx == 5'd16) begin
        sdram_wr <= 1'b1;
        sdram_base_addr <= stream_addr;
        sdram_wdata <= stream_buf;
        sdram_start <= 1'b1; sdram_done_latch <= 1'b0;
        stream_byte_idx <= 5'd0;
        stream_addr <= stream_addr + 24'd8;
    end else if (stream_remaining == 16'd0) begin
        resp[0] <= CMD_SDRAM_WRITE_STREAM; resp[1] <= ACK;
        resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
    end else if (rx_avail && stream_byte_idx < 5'd16) begin
        stream_buf[127 - (stream_byte_idx * 8) -: 8] <= rx_fifo[rx_rd];
        rx_rd <= rx_rd + 4'd1;
        stream_byte_idx <= stream_byte_idx + 5'd1;
        stream_remaining <= stream_remaining - 16'd1;
    end
end

S_SDRAM_FLASH_LOOP: begin
    if (loop_remaining == 24'd0 || loop_remaining[23]) begin
        resp[0] <= cmd_reg; resp[1] <= ACK;
        resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
    end else begin
        case (loop_phase)
            2'd0: begin
                sdram_wr <= 1'b0;
                sdram_base_addr <= loop_sdram_word;
                sdram_start <= 1'b1; sdram_done_latch <= 1'b0;
                loop_phase <= 2'd1;
            end
            2'd1: begin
                if (sdram_done_latch) begin
                    if (loop_flash_addr[15:0] == 16'd0) begin
                        spi_op <= 3'd4;
                        spi_addr <= loop_flash_addr;
                        spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                        loop_phase <= 2'd2;
                    end else begin
                        spi_op <= 3'd5;
                        spi_addr <= loop_flash_addr;
                        spi_prog_data <= sdram_rdata_latch;
                        spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                        loop_phase <= 2'd3;
                    end
                end
            end
            2'd2: begin
                if (spi_done_latch) begin
                    spi_op <= 3'd5;
                    spi_addr <= loop_flash_addr;
                    spi_prog_data <= sdram_rdata_latch;
                    spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                    loop_phase <= 2'd3;
                end
            end
            2'd3: begin
                if (spi_done_latch) begin
                    loop_flash_addr <= loop_flash_addr + 24'd16;
                    loop_sdram_word <= loop_sdram_word + 24'd8;
                    loop_remaining  <= loop_remaining - 24'd16;
                    loop_phase <= 2'd0;
                end
            end
        endcase
    end
end

S_RAW_WAIT_ACK: begin
    raw_req <= 1'b1;
    if (raw_ack) begin
        raw_req <= 1'b0;
        state <= S_RAW_WAIT_DONE;
    end
end

S_RAW_WAIT_DONE: begin
    if (cmd_reg == CMD_RAW_WRITE && raw_ready) begin
        raw_active <= 1'b0;
        resp[0] <= CMD_RAW_WRITE; resp[1] <= ACK;
        resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
    end else if (cmd_reg == CMD_RAW_READ && raw_valid) begin
        raw_active <= 1'b0;
        resp[0] <= CMD_RAW_READ;
        resp[1] <= raw_rdata[15:8];
        resp[2] <= raw_rdata[7:0];
        resp_len <= 5'd3; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
    end
end

S_SDRAM_VERIFY: begin
    if (loop_remaining == 24'd0 || loop_remaining[23]) begin
        resp[0] <= cmd_reg; resp[1] <= ACK;
        resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
    end else begin
        case (loop_phase)
            2'd0: begin
                sdram_wr <= 1'b0;
                sdram_base_addr <= loop_sdram_word;
                sdram_start <= 1'b1; sdram_done_latch <= 1'b0;
                loop_phase <= 2'd1;
            end
            2'd1: begin
                if (sdram_done_latch) begin
                    spi_op <= 3'd3;
                    spi_addr <= loop_flash_addr;
                    spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                    loop_phase <= 2'd2;
                end
            end
            2'd2: begin
                if (spi_done_latch) begin
                    spi_op <= 3'd3;
                    spi_addr <= loop_flash_addr;
                    spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                    loop_phase <= 2'd3;
                end
            end
            2'd3: begin
                if (spi_done_latch) begin
                    if (spi_read_data != sdram_rdata_latch) begin
                        resp[0] <= 8'hFF; resp[1] <= 8'h09;
                        resp[2] <= 8'd0; resp[3] <= {3'd0, state};
                        resp[4] <= cmd_reg; resp[5] <= 8'd0;
                        resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
                        resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
                        last_err_code <= 8'h09; last_err_cmd <= cmd_reg;
                        last_err_valid <= 1'b1; err_count <= err_count + 16'd1;
                        state <= S_TX_RESP;
                    end else begin
                        loop_flash_addr <= loop_flash_addr + 24'd16;
                        loop_sdram_word <= loop_sdram_word + 24'd8;
                        loop_remaining  <= loop_remaining - 24'd16;
                        loop_phase <= 2'd0;
                    end
                end
            end
        endcase
    end
end
