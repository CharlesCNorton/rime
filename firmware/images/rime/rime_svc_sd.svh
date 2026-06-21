// rime_svc_sd.svh — SD operation states extracted from rime_service.sv.
// `included inside the main FSM always_ff case block.
// States: S_WAIT_SD, S_SD_WRITE_RX, S_WAIT_INSTALL

S_WAIT_SD: begin
    if (sd_busy) sd_done_latch <= 1'b1;
    if (sd_done_latch && !sd_busy) begin
        if (!sd_ok) begin
            resp[0] <= 8'hFF; resp[1] <= 8'h07;
            resp[2] <= 8'd0; resp[3] <= {3'd0, state};
            resp[4] <= cmd_reg; resp[5] <= sd_last_error;
            resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
            resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
            last_err_code <= 8'h07; last_err_cmd <= cmd_reg;
            last_err_detail <= sd_last_error; last_err_valid <= 1'b1;
            err_count <= err_count + 16'd1;
            state <= S_TX_RESP;
        end else begin
            case (cmd_reg)
                CMD_SD_INIT: begin
                    resp[0] <= CMD_SD_INIT; resp[1] <= ACK;
                    resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                end
                CMD_SD_READ16: begin
                    resp[0]  <= CMD_SD_READ16;
                    resp[1]  <= sd_read_data[127:120];
                    resp[2]  <= sd_read_data[119:112];
                    resp[3]  <= sd_read_data[111:104];
                    resp[4]  <= sd_read_data[103:96];
                    resp[5]  <= sd_read_data[95:88];
                    resp[6]  <= sd_read_data[87:80];
                    resp[7]  <= sd_read_data[79:72];
                    resp[8]  <= sd_read_data[71:64];
                    resp[9]  <= sd_read_data[63:56];
                    resp[10] <= sd_read_data[55:48];
                    resp[11] <= sd_read_data[47:40];
                    resp[12] <= sd_read_data[39:32];
                    resp[13] <= sd_read_data[31:24];
                    resp[14] <= sd_read_data[23:16];
                    resp[15] <= sd_read_data[15:8];
                    resp[16] <= sd_read_data[7:0];
                    resp_len <= 5'd17; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                end
                CMD_SD_CRC32: begin
                    resp[0] <= CMD_SD_CRC32;
                    resp[1] <= sd_read_crc32[31:24];
                    resp[2] <= sd_read_crc32[23:16];
                    resp[3] <= sd_read_crc32[15:8];
                    resp[4] <= sd_read_crc32[7:0];
                    resp_len <= 5'd5; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                end
                CMD_SD_CRC32_RANGE: begin
                    if (crc_range_done) begin
                        resp[0] <= CMD_SD_CRC32_RANGE;
                        resp[1] <= crc_range_result[31:24];
                        resp[2] <= crc_range_result[23:16];
                        resp[3] <= crc_range_result[15:8];
                        resp[4] <= crc_range_result[7:0];
                        resp_len <= 5'd5; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                    end
                end
                CMD_SD_WRITE512: begin
                    resp[0] <= CMD_SD_WRITE512; resp[1] <= ACK;
                    resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                end
                default: begin
                    resp[0] <= cmd_reg; resp[1] <= ACK;
                    resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                end
            endcase
        end
    end
end

S_SD_WRITE_RX: begin
    if (rx_avail && didx < 10'd512) begin
        sd_load_addr <= didx[8:0];
        sd_load_data <= rx_fifo[rx_rd];
        sd_load_en   <= 1'b1;
        rx_rd <= rx_rd + 4'd1;
        didx  <= didx + 10'd1;
        stream_idle_cnt <= STREAM_TIMEOUT;
    end else if (didx == 10'd512) begin
        sd_op <= 3'd4;
        sd_start <= 1'b1; sd_done_latch <= 1'b0; sd_ok_latch <= 1'b0;
        state <= S_WAIT_SD;
    end else if (stream_idle_cnt == 24'd0) begin
        resp[0] <= 8'hFF; resp[1] <= 8'h04;
        resp[2] <= 8'd0; resp[3] <= {3'd0, state};
        resp[4] <= CMD_SD_WRITE512; resp[5] <= 8'd0;
        resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
        resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
        last_err_code <= 8'h04; last_err_cmd <= CMD_SD_WRITE512;
        last_err_detail <= 8'd0; last_err_valid <= 1'b1;
        err_count <= err_count + 16'd1;
        state <= S_TX_RESP;
    end else begin
        stream_idle_cnt <= stream_idle_cnt - 24'd1;
    end
end

// Cure list item #19. The sd_install_engine drives flash and SD
// master directly via the top.sv mux while install_active is high.
// We sit here until install_done; then drop install_active so the
// service regains the buses, and emit ACK or 8-byte error frame.
S_WAIT_INSTALL: begin
    if (install_done) begin
        install_active <= 1'b0;
        if (install_ok) begin
            resp[0] <= CMD_SD_INSTALL; resp[1] <= ACK;
            resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
            state <= S_TX_RESP;
        end else begin
            resp[0] <= 8'hFF;
            resp[1] <= install_error_code;
            resp[2] <= 8'd0; resp[3] <= {3'd0, state};
            resp[4] <= CMD_SD_INSTALL;
            resp[5] <= install_error_detail;
            resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
            resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
            last_err_code <= install_error_code;
            last_err_cmd  <= CMD_SD_INSTALL;
            last_err_detail <= install_error_detail;
            last_err_valid <= 1'b1;
            err_count <= err_count + 16'd1;
            state <= S_TX_RESP;
        end
    end
end
