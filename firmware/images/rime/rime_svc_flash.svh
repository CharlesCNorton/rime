// rime_svc_flash.svh — Flash operation states extracted from rime_service.sv.
// `included inside the main FSM always_ff case block.
// States: S_WAIT_SPI

S_WAIT_SPI: begin
    if (spi_done_latch) begin
        case (cmd_reg)
            CMD_JEDEC: begin
                resp[0] <= CMD_JEDEC;
                resp[1] <= spi_jedec[23:16];
                resp[2] <= spi_jedec[15:8];
                resp[3] <= spi_jedec[7:0];
                resp_len <= 5'd4;
            end
            CMD_STATUS: begin
                resp[0] <= CMD_STATUS;
                resp[1] <= spi_status[7:0];
                resp[2] <= spi_status[15:8];
                resp_len <= 5'd3;
            end
            CMD_READ16: begin
                resp[0]  <= CMD_READ16;
                resp[1]  <= spi_read_data[127:120];
                resp[2]  <= spi_read_data[119:112];
                resp[3]  <= spi_read_data[111:104];
                resp[4]  <= spi_read_data[103:96];
                resp[5]  <= spi_read_data[95:88];
                resp[6]  <= spi_read_data[87:80];
                resp[7]  <= spi_read_data[79:72];
                resp[8]  <= spi_read_data[71:64];
                resp[9]  <= spi_read_data[63:56];
                resp[10] <= spi_read_data[55:48];
                resp[11] <= spi_read_data[47:40];
                resp[12] <= spi_read_data[39:32];
                resp[13] <= spi_read_data[31:24];
                resp[14] <= spi_read_data[23:16];
                resp[15] <= spi_read_data[15:8];
                resp[16] <= spi_read_data[7:0];
                resp_len <= 5'd17;
            end
            default: begin
                resp[0] <= cmd_reg; resp[1] <= spi_ok_latch ? ACK : 8'hEE;
                resp_len <= 5'd2;
            end
        endcase
        resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
        state <= S_TX_RESP;
    end
end
