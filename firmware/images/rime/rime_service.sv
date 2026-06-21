// Section index (line numbers are approximate; search for the label):
//   PORTS             — module port declarations
//   COMMAND_IDS       — localparam CMD_* constants (canonical copy also in rime_service_defs.svh)
//   CAPS              — capability bitmasks (CAPS0, CAPS1, CAPS2)
//   APP_MODE_LEDS     — LED pattern generator and app_mode register
//   TX_FIFO / RX_FIFO — 16-deep transmit and receive FIFOs
//   DONE_LATCHES      — spi_done_latch, sd_done_latch, sdram_done_latch
//   COUNTERS          — cmd/erase/prog/err counters, uptime, reset arm
//   FSM_STATES        — localparam S_* state encoding (5-bit, 17 states)
//   FSM_REGISTERS     — state, cmd_reg, resp[], rxb[], stream vars
//   MAIN_FSM          — always_ff: the single monolithic FSM
//
// rime_service_defs.svh contains an extracted copy of all command IDs,
// capability flags, and FSM state encodings. The definitions here remain
// authoritative for this image; the .svh must be kept in sync.
//     S_IDLE           — wait for UART byte
//     S_DISPATCH       — app mode vs service mode command decode
//     S_TX_RESP        — drain response FIFO
//     S_RX_BYTES       — collect multi-byte payload + per-command decode
//     S_WAIT_SPI       — poll flash SPI
//     S_WAIT_SDRAM     — poll SDRAM bridge
//     S_SDRAM_STREAM   — bulk UART→SDRAM
//     S_SDRAM_FLASH_LOOP — on-board erase/program
//     S_SDRAM_VERIFY   — on-board SDRAM vs flash compare
//     S_RAW_*          — single-word SDRAM access
//     S_WAIT_SD        — poll SD SPI master
//     S_SD_WRITE_RX    — receive 512 bytes
//     S_WAIT_INSTALL   — wait for sd_install_engine
module rime_service #(
    parameter integer CLK_HZ = 25000000
) (
    input  wire        clk,
    input  wire        rst,

    input  wire        uart_rx_valid,
    input  wire [7:0]  uart_rx_data,
    output logic       uart_tx_send,
    output logic [7:0] uart_tx_data,
    input  wire        uart_tx_busy,
    // (* keep *) prevents the synthesizer constant-folding away the frame_done
    // pulse that the top.sv CRC injector watches. Without this attribute
    // the resp drain transition gets optimized into the FIFO empty signal
    // and the CRC byte never gets injected on silicon. (todo.md item 2.)
    (* keep *) output logic uart_tx_frame_done,

    output logic [2:0]  spi_op,
    output logic [23:0] spi_addr,
    output logic [127:0] spi_prog_data,
    output logic        spi_start,
    input  wire         spi_busy,
    input  wire         spi_done,
    input  wire         spi_ok,
    input  wire [127:0] spi_read_data,
    input  wire [15:0]  spi_status,
    input  wire [23:0]  spi_jedec,

    output logic        sdram_start,
    output logic        sdram_wr,
    output logic [23:0] sdram_base_addr,
    output logic [127:0] sdram_wdata,
    input  wire  [127:0] sdram_rdata,
    input  wire         sdram_done,
    input  wire         sdram_busy,
    input  wire         sdram_init_done,

    output logic       busy,
    output logic [4:0] gpio_led,

    output logic        raw_req,
    output logic        raw_wr,
    output logic [23:0] raw_addr,
    output logic [15:0] raw_wdata,
    input  wire  [15:0] raw_rdata,
    input  wire         raw_ready,
    input  wire         raw_valid,
    input  wire         raw_ack,
    output logic        raw_active,

    output logic        sd_start,
    output logic [2:0]  sd_op,
    output logic [31:0] sd_lba,
    output logic [4:0]  sd_chunk_idx,
    input  wire         sd_busy,
    input  wire         sd_done,
    input  wire         sd_ok,
    input  wire         sd_card_present,
    input  wire         sd_initialized,
    input  wire         sd_high_capacity,
    input  wire [7:0]   sd_last_error,
    input  wire [7:0]   sd_last_r1,
    input  wire [127:0] sd_read_data,
    input  wire [31:0]  sd_read_crc32,
    output logic [8:0]  sd_write_addr,
    input  wire  [7:0]  sd_write_data,
    output logic [8:0]  sd_load_addr,
    output logic [7:0]  sd_load_data,
    output logic        sd_load_en,
    input  wire         sd_det_in,
    output logic        reset_request,
    output logic        watchdog_set_pulse,
    output logic [31:0] watchdog_set_value,
    output logic        crc_range_start,
    output logic [31:0] crc_range_lba,
    output logic [15:0] crc_range_count,
    input  wire         crc_range_done,
    input  wire  [31:0] crc_range_result,

    input  wire [4:0]   sd_dbg_state,
    input  wire [7:0]   sd_dbg_shift_in,
    input  wire         sd_dbg_shift_busy,

    // Cure list item #19: host-driven SD bundle install path.
    // install_active is held high while the engine is running so the
    // top.sv mux routes the SPI flash and SD master interfaces from
    // sd_install_engine instead of this service. install_start is a
    // one-cycle pulse that kicks the engine off with bundle_lba.
    output logic        install_start,
    output logic        install_active,
    output logic [31:0] install_lba,
    input  wire         install_done,
    input  wire         install_ok,
    input  wire  [7:0]  install_error_code,
    input  wire  [7:0]  install_error_detail,

    input  wire         recovery_hold,
    input  wire  [2:0]  recovery_exit_reason,
    input  wire  [7:0]  recovery_exit_detail
);

    `include "rime_service_defs.svh"

    // (* keep *) prevents the synthesizer constant-folding app_mode.
    // New state logic in this always_ff has historically triggered an
    // optimizer fold of app_mode to 1, breaking ENTER_SERVICE.
    (* keep *) logic app_mode;
    logic [24:0] led_cnt;
    wire  [3:0]  led_phase = led_cnt[24:21];
    reg   [3:0]  svc_led_pattern;
    always_comb begin
        case (led_phase)
            4'd0:  svc_led_pattern = 4'b0001;
            4'd1:  svc_led_pattern = 4'b0001;
            4'd2:  svc_led_pattern = 4'b0010;
            4'd3:  svc_led_pattern = 4'b0010;
            4'd4:  svc_led_pattern = 4'b0100;
            4'd5:  svc_led_pattern = 4'b0100;
            4'd6:  svc_led_pattern = 4'b1000;
            4'd7:  svc_led_pattern = 4'b1000;
            4'd8:  svc_led_pattern = 4'b0100;
            4'd9:  svc_led_pattern = 4'b0100;
            4'd10: svc_led_pattern = 4'b0010;
            4'd11: svc_led_pattern = 4'b0010;
            4'd12: svc_led_pattern = 4'b0001;
            4'd13: svc_led_pattern = 4'b0001;
            4'd14: svc_led_pattern = 4'b0000;
            4'd15: svc_led_pattern = 4'b0000;
        endcase
    end
    wire [3:0] app_led_pattern = led_cnt[23] ? 4'b1111 : 4'b0000;

    logic [7:0]  tx_fifo [0:15];
    logic [3:0]  tx_wr, tx_rd;
    wire         tx_empty = (tx_wr == tx_rd);
    wire         tx_full  = ((tx_wr + 4'd1) == tx_rd);

    always_ff @(posedge clk) begin
        uart_tx_send <= 1'b0;
        if (rst)
            tx_rd <= 4'd0;
        else if (!tx_empty && !uart_tx_busy && !uart_tx_send) begin
            uart_tx_data <= tx_fifo[tx_rd];
            uart_tx_send <= 1'b1;
            tx_rd <= tx_rd + 4'd1;
        end
    end

    logic [7:0]  rx_fifo [0:15];
    logic [3:0]  rx_wr, rx_rd;
    wire         rx_avail = (rx_wr != rx_rd);

    always_ff @(posedge clk) begin
        if (rst)
            rx_wr <= 4'd0;
        else if (uart_rx_valid && ((rx_wr + 4'd1) != rx_rd)) begin
            rx_fifo[rx_wr] <= uart_rx_data;
            rx_wr <= rx_wr + 4'd1;
        end
    end

    logic spi_done_latch, spi_ok_latch;
    logic sd_done_latch, sd_ok_latch;

    logic sdram_done_latch;
    logic [127:0] sdram_rdata_latch;

    logic [15:0] cmd_count, erase_count, prog_count, err_count;
    logic [7:0]  last_err_code, last_err_cmd, last_err_detail;
    logic        last_err_valid;
    logic        reset_armed;
    logic [23:0] reset_counter;
    // Write-unlock semantics: every CMD_ERASE64 and CMD_PROGRAM16 payload
    // carries an inline 4-byte "RIME" prefix. There is no stateful flag
    // and no expiry timer — the key validates per-operation. This makes
    // unlock-replay attacks impossible and removes the 670 ms timer that
    // forced hosts to re-unlock during long bulk operations.

    logic [24:0] uptime_tick;
    logic [31:0] uptime_secs;
    always_ff @(posedge clk) begin
        if (rst) begin
            uptime_tick <= 25'd0;
            uptime_secs <= 32'd0;
        end else begin
            if (uptime_tick >= CLK_HZ - 1) begin
                uptime_tick <= 25'd0;
                uptime_secs <= uptime_secs + 32'd1;
            end else begin
                uptime_tick <= uptime_tick + 25'd1;
            end
        end
    end

    always_ff @(posedge clk) begin
        reset_request <= 1'b0;
        if (rst) begin
            reset_armed <= 1'b0;
            reset_counter <= 24'd0;
        end else if (reset_armed) begin
            if (tx_empty && !uart_tx_busy) begin
                if (reset_counter > 24'd250000)
                    reset_request <= 1'b1;
                else
                    reset_counter <= reset_counter + 24'd1;
            end
        end
    end

    // FSM states are defined in rime_service_defs.svh (included above).


    logic [4:0]  state;
    logic [7:0]  cmd_reg;

    // Max response is 17 bytes (CMD echo + 16 data). Entries 17-19
    // were never written, producing undriven-net warnings that fed
    // downstream constant-folding in synthesis.
    logic [7:0]  resp [0:16];
    logic [4:0]  resp_len, resp_idx;
    logic [7:0]  resp_crc;
    logic        resp_crc_pending;  // retained as a benign no-op; framing is now unconditional

    // Length-prefixed TX framing: every response goes out as
    //   [type, len_lo, len_hi, payload(resp_len), crc8]
    // where type is 0x02 for error frames (resp[0]==0xFF) else 0x01, and crc8
    // covers the header+payload. S_TX_RESP walks resp_idx over header then payload.
    localparam [7:0] FRAME_RESPONSE = 8'h01;
    localparam [7:0] FRAME_ERROR    = 8'h02;
    wire [7:0] frame_type_lp = (resp[0] == 8'hFF) ? FRAME_ERROR : FRAME_RESPONSE;
    wire [4:0] payload_i_lp  = (resp_idx >= 5'd3) ? (resp_idx - 5'd3) : 5'd0;
    wire [7:0] tx_byte_lp =
        (resp_idx == 5'd0) ? frame_type_lp :
        (resp_idx == 5'd1) ? {3'd0, resp_len} :
        (resp_idx == 5'd2) ? 8'd0 :
                             resp[payload_i_lp];

    function automatic [7:0] svc_crc8(input [7:0] c, input [7:0] d);
        svc_crc8[0] = c[0]^c[6]^c[7]^d[0]^d[6]^d[7];
        svc_crc8[1] = c[0]^c[1]^c[6]^d[0]^d[1]^d[6];
        svc_crc8[2] = c[0]^c[1]^c[2]^c[6]^d[0]^d[1]^d[2]^d[6];
        svc_crc8[3] = c[1]^c[2]^c[3]^c[7]^d[1]^d[2]^d[3]^d[7];
        svc_crc8[4] = c[2]^c[3]^c[4]^d[2]^d[3]^d[4];
        svc_crc8[5] = c[3]^c[4]^c[5]^d[3]^d[4]^d[5];
        svc_crc8[6] = c[4]^c[5]^c[6]^d[4]^d[5]^d[6];
        svc_crc8[7] = c[5]^c[6]^c[7]^d[5]^d[6]^d[7];
    endfunction

    logic [7:0]  rxb [0:23];   // up to 24 bytes (PROGRAM16 = 4 key + 3 addr + 16 data + 1 slack)
    logic [4:0]  rx_need, rx_got;

    logic [2:0]  raw_word_idx;
    logic [127:0] raw_rdata_buf;

    logic [23:0] loop_flash_addr;
    logic [23:0] loop_sdram_word;
    logic [23:0] loop_remaining;
    logic [1:0]  loop_phase;

    logic [9:0]  didx;

    logic [23:0] stream_addr;
    logic [15:0] stream_remaining;
    logic [4:0]  stream_byte_idx;
    logic [127:0] stream_buf;
    logic [23:0] stream_idle_cnt;
    localparam [23:0] STREAM_TIMEOUT = 24'hFFFFFF;

    logic [23:0] sdram_stream_wdog;
    logic        sdram_stream_wdog_expired;
    always_ff @(posedge clk) begin
        if (rst || state != S_SDRAM_STREAM) begin
            sdram_stream_wdog <= STREAM_TIMEOUT;
            sdram_stream_wdog_expired <= 1'b0;
        end else if (rx_avail || stream_byte_idx == 5'd16) begin
            sdram_stream_wdog <= STREAM_TIMEOUT;
        end else if (sdram_stream_wdog == 24'd0) begin
            sdram_stream_wdog_expired <= 1'b1;
        end else begin
            sdram_stream_wdog <= sdram_stream_wdog - 24'd1;
        end
    end

    always_ff @(posedge clk) begin
        spi_start   <= 1'b0;
        sdram_start <= 1'b0;
        sd_start    <= 1'b0;
        sd_load_en  <= 1'b0;
        watchdog_set_pulse <= 1'b0;
        crc_range_start    <= 1'b0;
        uart_tx_frame_done <= 1'b0;
        install_start      <= 1'b0;  // pulse only

        // Done-latches: start-clears-first priority prevents a stale done=1
        // from a previous operation from immediately re-latching on the same
        // cycle as a new start pulse. The else-if structure guarantees that
        // start always wins over done when both are asserted simultaneously.
        if (spi_start)      begin spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0; end
        else if (spi_done)  begin spi_done_latch <= 1'b1; spi_ok_latch <= spi_ok; end
        if (sdram_start)      begin sdram_done_latch <= 1'b0; end
        else if (sdram_done)  begin sdram_done_latch <= 1'b1; sdram_rdata_latch <= sdram_rdata; end
        if (sd_start)      begin sd_done_latch <= 1'b0; sd_ok_latch <= 1'b0; end
        else if (sd_done)  begin sd_done_latch <= 1'b1; sd_ok_latch <= sd_ok; end

        if (rst) begin
            spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
            sdram_done_latch <= 1'b0; sdram_rdata_latch <= 128'd0;
            sd_done_latch <= 1'b0; sd_ok_latch <= 1'b0;
            raw_req <= 1'b0; raw_wr <= 1'b0; raw_addr <= 24'd0;
            raw_wdata <= 16'd0; raw_active <= 1'b0;
            install_active <= 1'b0;
            install_lba <= 32'd0;
            state      <= S_IDLE;
            tx_wr      <= 4'd0;
            rx_rd      <= 4'd0;
            gpio_led   <= 5'b00001;
            app_mode   <= 1'b1;
            led_cnt    <= 25'd0;
            busy       <= 1'b0;
            cmd_count  <= 16'd0;
            erase_count <= 16'd0;
            prog_count <= 16'd0;
            err_count  <= 16'd0;
            last_err_valid <= 1'b0;
            resp_len   <= 5'd0;
            resp_idx   <= 5'd0; resp_crc_pending <= CAPS0[7];
            resp_crc   <= 8'd0;
            resp_crc_pending <= 1'b0;
            rx_need    <= 5'd0;
            rx_got     <= 5'd0;
        end else begin

            case (state)
                S_IDLE: begin
                    busy <= 1'b0;
                    led_cnt <= led_cnt + 25'd1;
                    if (app_mode)
                        gpio_led <= {1'b0, app_led_pattern};
                    else
                        gpio_led <= {1'b0, svc_led_pattern};
                    if (rx_avail) begin
                        cmd_reg <= rx_fifo[rx_rd];
                        rx_rd   <= rx_rd + 4'd1;
                        cmd_count <= cmd_count + 16'd1;
                        state   <= S_DISPATCH;
                        busy    <= 1'b1;
                    end
                end

                // Command dispatch: app_mode gates which commands are available.
                // App mode: HELLO, PING, ENTER_SERVICE, UNLOCK, UPTIME, IDENTITY.
                // Service mode: all flash, SDRAM, SD, raw, system commands.
                S_DISPATCH: begin
                    stream_idle_cnt <= STREAM_TIMEOUT;
                    if (app_mode) begin
                        case (cmd_reg)
                            // 0x00 HELLO: report mode (app).
                            CMD_HELLO: begin
                                resp[0] <= CMD_HELLO; resp[1] <= MODE_APP;
                                resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                            end
                            // 0x01 PING: respond with ACK byte (0xAC)
                            CMD_PING: begin
                                resp[0] <= CMD_PING; resp[1] <= ACK;
                                resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                            end
                            // 0x02 ENTER_SERVICE: clear app_mode, respond ACK
                            CMD_ENTER_SERVICE: begin
                                app_mode <= 1'b0;
                                resp[0] <= CMD_ENTER_SERVICE; resp[1] <= ACK;
                                resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                            end
                            // 0x03 UNLOCK: receive 4-byte key "RIME", validate in S_RX_BYTES
                            CMD_UNLOCK: begin
                                rx_need <= 5'd4; rx_got <= 5'd0; state <= S_RX_BYTES;
                            end
                            // 0x05 UPTIME: respond with 32-bit big-endian seconds since boot
                            CMD_UPTIME: begin
                                resp[0] <= CMD_UPTIME;
                                resp[1] <= uptime_secs[31:24];
                                resp[2] <= uptime_secs[23:16];
                                resp[3] <= uptime_secs[15:8];
                                resp[4] <= uptime_secs[7:0];
                                resp_len <= 5'd5; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                            end
                            // 0x06 IDENTITY: respond with "RIME" + mode flag.
                            CMD_IDENTITY: begin
                                resp[0]  <= CMD_IDENTITY;
                                resp[1]  <= 8'h52;  // 'R'
                                resp[2]  <= 8'h49;  // 'I'
                                resp[3]  <= 8'h4D;  // 'M'
                                resp[4]  <= 8'h45;  // 'E'
                                resp[5]  <= {7'd0, app_mode};
                                resp_len <= 5'd6; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                            end
                            // Unknown command in app mode: full 8-byte error frame
                            // [0xFF, code, state_hi, state_lo, command, detail, flags, spi_op]
                            // matching PROTOCOL.md spec.
                            default: begin
                                resp[0] <= 8'hFF;
                                resp[1] <= 8'h01;            // ERR_UNKNOWN_CMD
                                resp[2] <= 8'd0;             // state_hi
                                resp[3] <= {3'd0, state};    // state_lo
                                resp[4] <= cmd_reg;          // command
                                resp[5] <= 8'd0;             // detail
                                resp[6] <= 8'd0;             // flags
                                resp[7] <= 8'd0;             // spi_op
                                resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
                                err_count <= err_count + 16'd1;
                                state <= S_TX_RESP;
                            end
                        endcase
                    end else begin
                    // === SERVICE MODE DISPATCH ===
                    case (cmd_reg)
                        // 0x00 HELLO: report mode (service).
                        CMD_HELLO: begin
                            resp[0] <= CMD_HELLO; resp[1] <= MODE_SERVICE;
                            resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x01 PING: respond with ACK (0xAC)
                        CMD_PING: begin
                            resp[0] <= CMD_PING; resp[1] <= ACK;
                            resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x73 INFO: respond with caps + flash geometry.
                        // [caps0, caps1, max_prog=16, read_chunk=16, erase_log2=16, page_log2=8, addr_bytes=3]
                        CMD_INFO: begin
                            resp[0] <= CMD_INFO;
                            resp[1] <= CAPS0; resp[2] <= CAPS1;
                            resp[3] <= 8'd16;   // max_program: 16 bytes per PROGRAM16
                            resp[4] <= 8'd16;   // read_chunk: 16 bytes per READ16
                            resp[5] <= 8'd16;   // erase_log2: 2^16 = 64 KiB sectors
                            resp[6] <= 8'd8;    // page_log2: 2^8 = 256-byte pages
                            resp[7] <= 8'd3;    // addr_bytes: 3-byte flash addresses
                            resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x74 JEDEC: start SPI JEDEC-ID read, wait in S_WAIT_SPI
                        // Response assembled in S_WAIT_SPI: [cmd, mfr, dev, cap]
                        CMD_JEDEC: begin
                            spi_op <= 3'd1; spi_addr <= 24'd0; spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                            state <= S_WAIT_SPI;
                        end
                        // 0x71 STATUS: start SPI status-register read, wait in S_WAIT_SPI
                        // Response: [cmd, sr1, sr2]
                        CMD_STATUS: begin
                            spi_op <= 3'd2; spi_addr <= 24'd0; spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                            state <= S_WAIT_SPI;
                        end
                        // 0x72 READ16: receive 3-byte address, then SPI read 16 bytes
                        CMD_READ16: begin
                            rx_need <= 5'd3; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x75 ERASE64: 4-byte "RIME" key + 3-byte sector address (7 bytes total).
                        CMD_ERASE64: begin
                            rx_need <= 5'd7; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x70 PROGRAM16: 4-byte "RIME" key + 3-byte address + 16 data (23 bytes total).
                        CMD_PROGRAM16: begin
                            rx_need <= 5'd23; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x76 LAST_ERROR: respond with stored error code, command, detail, valid flag
                        CMD_LAST_ERROR: begin
                            resp[0] <= CMD_LAST_ERROR;
                            resp[1] <= last_err_code; resp[2] <= last_err_cmd;
                            resp[3] <= last_err_detail;
                            resp[4] <= 8'd0; resp[5] <= 8'd0;
                            resp[6] <= {7'd0, last_err_valid};
                            resp_len <= 5'd7; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x77 STATS: respond with 16-bit counters for cmds, erases, programs, errors
                        CMD_STATS: begin
                            resp[0] <= CMD_STATS;
                            resp[1] <= cmd_count[15:8]; resp[2] <= cmd_count[7:0];
                            resp[3] <= erase_count[15:8]; resp[4] <= erase_count[7:0];
                            resp[5] <= prog_count[15:8]; resp[6] <= prog_count[7:0];
                            resp[7] <= err_count[15:8]; resp[8] <= err_count[7:0];
                            resp_len <= 5'd9; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x78 CLEAR_ERROR: clear the latched error state, respond ACK
                        CMD_CLEAR_ERROR: begin
                            last_err_valid <= 1'b0;
                            resp[0] <= CMD_CLEAR_ERROR; resp[1] <= ACK;
                            resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x79 DEBUG: respond with internal FSM state, command, SPI op, flags
                        CMD_DEBUG: begin
                            resp[0] <= CMD_DEBUG; resp[1] <= 8'd0;  // reserved
                            resp[2] <= {3'd0, state}; resp[3] <= cmd_reg;
                            resp[4] <= {5'd0, spi_op};
                            resp[5]  <= 8'd0; resp[6]  <= 8'd0; resp[7]  <= 8'd0;
                            resp[8]  <= 8'd0; resp[9]  <= 8'd0;
                            resp[10] <= {7'd0, recovery_hold};
                            resp[11] <= {5'd0, recovery_exit_reason};
                            resp[12] <= recovery_exit_detail;
                            resp[13] <= 8'd0;
                            resp_len <= 5'd14; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x80 SDRAM_INFO: respond with init_done flag and CAPS2 bitmask
                        CMD_SDRAM_INFO: begin
                            resp[0] <= CMD_SDRAM_INFO;
                            resp[1] <= {7'd0, sdram_init_done};
                            resp[2] <= CAPS2;
                            resp_len <= 5'd3; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x81 SDRAM_READ16: receive 3-byte word address, read 16 bytes (8 words)
                        CMD_SDRAM_READ16: begin
                            rx_need <= 5'd3; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x82 SDRAM_WRITE16: receive 3-byte word address + 16 data bytes
                        CMD_SDRAM_WRITE16: begin
                            rx_need <= 5'd19; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x84 SDRAM_WRITE_STREAM: receive 3-byte addr + 2-byte length, then bulk data
                        // Transitions to S_SDRAM_STREAM for byte-at-a-time UART→SDRAM transfer
                        CMD_SDRAM_WRITE_STREAM: begin
                            rx_need <= 5'd5; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x83 SDRAM_TO_FLASH: receive 3-byte flash addr + 3-byte count
                        // Runs erase→program loop on-board at SPI speed in S_SDRAM_FLASH_LOOP
                        CMD_SDRAM_TO_FLASH: begin
                            rx_need <= 5'd6; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x85 SDRAM_VERIFY_FLASH: receive 3-byte flash addr + 3-byte count
                        // Compares SDRAM word 0 against flash on-board in S_SDRAM_VERIFY
                        CMD_SDRAM_VERIFY_FLASH: begin
                            rx_need <= 5'd6; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x90 RAW_WRITE: receive 3-byte word addr + 2-byte data (single 16-bit word)
                        CMD_RAW_WRITE: begin
                            rx_need <= 5'd5; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x91 RAW_READ: receive 3-byte word addr, respond with 2-byte data
                        CMD_RAW_READ: begin
                            rx_need <= 5'd3; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x7A SD_INFO: respond with card flags, error state, chunk geometry
                        CMD_SD_INFO: begin
                            resp[0] <= CMD_SD_INFO;
                            resp[1] <= {4'd0, sd_det_in, sd_high_capacity, sd_initialized, sd_card_present};
                            resp[2] <= sd_last_error;
                            resp[3] <= sd_last_r1;
                            resp[4] <= 8'd16;   // chunk_bytes
                            resp[5] <= 8'd32;   // chunks_per_block (512/16)
                            resp[6] <= {3'd0, sd_dbg_state};
                            resp[7] <= sd_dbg_shift_in;
                            resp[8] <= {7'd0, sd_dbg_shift_busy};
                            resp[9] <= {3'd0, state};
                            resp_len <= 5'd10; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x7B SD_INIT: start SD card SPI initialization sequence, wait in S_WAIT_SD
                        CMD_SD_INIT: begin
                            sd_op <= 3'd1; sd_lba <= 32'd0; sd_start <= 1'b1; sd_done_latch <= 1'b0; sd_ok_latch <= 1'b0;
                            stream_idle_cnt <= 24'hFFFFFF;
                            state <= S_WAIT_SD;
                        end
                        // 0x7C SD_READ16: receive 4-byte LBA + 1-byte chunk index, read 16 bytes
                        CMD_SD_READ16: begin
                            rx_need <= 5'd5; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x6F SD_CRC32_RANGE: receive 4-byte LBA + 2-byte count
                        CMD_SD_CRC32_RANGE: begin
                            rx_need <= 5'd6; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x7E SD_CRC32: receive 4-byte LBA, compute CRC-32 of entire 512-byte block
                        CMD_SD_CRC32: begin
                            rx_need <= 5'd4; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x7F SD_WRITE512: receive 4-byte LBA, then 512 data bytes in S_SD_WRITE_RX
                        CMD_SD_WRITE512: begin
                            rx_need <= 5'd4; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x7D SD_INSTALL: receive 4-byte bundle LBA, then run the
                        // sd_install_engine via top.sv mux. Cure list item #19.
                        CMD_SD_INSTALL: begin
                            rx_need <= 5'd4; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x86 SW_RESET: respond ACK, then arm reset counter (fires after TX drains)
                        CMD_SW_RESET: begin
                            resp[0] <= CMD_SW_RESET; resp[1] <= ACK;
                            resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
                            reset_armed <= 1'b1;
                            state <= S_TX_RESP;
                        end
                        // 0x87 SET_WATCHDOG: receive 4-byte cycle count, ACK (no-op for now)
                        CMD_SET_WATCHDOG: begin
                            rx_need <= 5'd4; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x03 UNLOCK: receive 4-byte key "RIME" (0x52494D45), set write_unlocked
                        // Consumed by next ERASE64/PROGRAM16; expires after ~670ms
                        CMD_UNLOCK: begin
                            rx_need <= 5'd4; rx_got <= 5'd0; state <= S_RX_BYTES;
                        end
                        // 0x04 EXIT_SERVICE: set app_mode, respond ACK
                        CMD_EXIT_SERVICE: begin
                            app_mode <= 1'b1;
                            resp[0] <= CMD_EXIT_SERVICE; resp[1] <= ACK;
                            resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x05 UPTIME: respond with 32-bit big-endian seconds since boot
                        CMD_UPTIME: begin
                            resp[0] <= CMD_UPTIME;
                            resp[1] <= uptime_secs[31:24];
                            resp[2] <= uptime_secs[23:16];
                            resp[3] <= uptime_secs[15:8];
                            resp[4] <= uptime_secs[7:0];
                            resp_len <= 5'd5; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // 0x06 IDENTITY: respond with "RIME" + mode flag.
                        CMD_IDENTITY: begin
                            resp[0]  <= CMD_IDENTITY;
                            resp[1]  <= 8'h52;  // 'R'
                            resp[2]  <= 8'h49;  // 'I'
                            resp[3]  <= 8'h4D;  // 'M'
                            resp[4]  <= 8'h45;  // 'E'
                            resp[5]  <= {7'd0, app_mode};
                            resp_len <= 5'd6; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                        end
                        // Unknown command in service mode: full 8-byte error frame.
                        default: begin
                            resp[0] <= 8'hFF;
                            resp[1] <= 8'h01;            // ERR_UNKNOWN_CMD
                            resp[2] <= 8'd0;             // state_hi
                            resp[3] <= {3'd0, state};    // state_lo
                            resp[4] <= cmd_reg;          // command
                            resp[5] <= 8'd0;             // detail
                            resp[6] <= 8'd0;             // flags
                            resp[7] <= {5'd0, spi_op};   // spi_op
                            resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
                            last_err_code <= 8'h01; last_err_cmd <= cmd_reg;
                            last_err_detail <= 8'd0; last_err_valid <= 1'b1;
                            err_count <= err_count + 16'd1;
                            state <= S_TX_RESP;
                        end
                    endcase
                    end
                end

                S_TX_RESP: begin
                    // Single framing: [type, len_lo, len_hi, payload, crc8].
                    // type 0x02 = error frame (resp[0]==0xFF), else 0x01.
                    // crc8 covers header + payload. resp_idx walks header (0..2)
                    // then payload (3..2+resp_len), then one CRC byte.
                    if (resp_idx < (5'd3 + resp_len) && !tx_full) begin
                        tx_fifo[tx_wr] <= tx_byte_lp;
                        tx_wr    <= tx_wr + 4'd1;
                        resp_crc <= (resp_idx == 5'd0)
                            ? svc_crc8(8'd0, tx_byte_lp)
                            : svc_crc8(resp_crc, tx_byte_lp);
                        resp_idx <= resp_idx + 5'd1;
                    end else if (resp_idx == (5'd3 + resp_len) && !tx_full) begin
                        tx_fifo[tx_wr] <= resp_crc;
                        tx_wr          <= tx_wr + 4'd1;
                        resp_idx       <= resp_idx + 5'd1;
                    end else if (resp_idx > (5'd3 + resp_len)) begin
                        uart_tx_frame_done <= 1'b1;
                        state <= S_IDLE;
                    end
                end

                S_RX_BYTES: begin
                    if (rx_avail && rx_got < rx_need) begin
                        rxb[rx_got] <= rx_fifo[rx_rd];
                        rx_rd  <= rx_rd + 4'd1;
                        rx_got <= rx_got + 5'd1;
                        stream_idle_cnt <= STREAM_TIMEOUT;
                    end else if (rx_got < rx_need) begin
                        if (stream_idle_cnt == 24'd0) begin
                            resp[0] <= 8'hFF; resp[1] <= 8'h04;
                            resp[2] <= 8'd0; resp[3] <= {3'd0, state};
                            resp[4] <= cmd_reg; resp[5] <= 8'd0;
                            resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
                            resp_len <= 5'd8; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7];
                            last_err_code <= 8'h04; last_err_cmd <= cmd_reg;
                            last_err_detail <= 8'd0; last_err_valid <= 1'b1;
                            err_count <= err_count + 16'd1;
                            state <= S_TX_RESP;
                        end else begin
                            stream_idle_cnt <= stream_idle_cnt - 24'd1;
                        end
                    end
                    if (rx_got >= rx_need) begin
                        case (cmd_reg)
                            CMD_READ16: begin
                                spi_op   <= 3'd3;
                                spi_addr <= {rxb[0], rxb[1], rxb[2]};
                                spi_start <= 1'b1; spi_done_latch <= 1'b0; spi_ok_latch <= 1'b0;
                                state <= S_WAIT_SPI;
                            end
                            CMD_ERASE64: begin
                                // ERASE64: validate inline 'RIME' prefix at rxb[0..3], addr at rxb[4..6]
                                if (rxb[0]!=8'h52 || rxb[1]!=8'h49 || rxb[2]!=8'h4D || rxb[3]!=8'h45) begin
                                    resp[0] <= 8'hFF; resp[1] <= 8'h01;
                                    resp[2] <= 8'd0; resp[3] <= {3'd0, state};
                                    resp[4] <= CMD_ERASE64; resp[5] <= 8'd0;
                                    resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
                                    resp_len<=5'd8; resp_idx<=5'd0; resp_crc_pending <= CAPS0[7];
                                    last_err_code<=8'h01; last_err_cmd<=CMD_ERASE64;
                                    last_err_detail<=8'd0; last_err_valid<=1'b1;
                                    err_count<=err_count+16'd1; state<=S_TX_RESP;
                                end else begin
                                    spi_op<=3'd4; spi_addr<={rxb[4],rxb[5],rxb[6]};
                                    spi_start<=1'b1; spi_done_latch<=1'b0; spi_ok_latch<=1'b0;
                                    erase_count<=erase_count+16'd1; state<=S_WAIT_SPI;
                                end
                            end
                            CMD_PROGRAM16: begin
                                // PROGRAM16: 'RIME' at rxb[0..3], addr at rxb[4..6], data at rxb[7..22]
                                if (rxb[0]!=8'h52 || rxb[1]!=8'h49 || rxb[2]!=8'h4D || rxb[3]!=8'h45) begin
                                    resp[0] <= 8'hFF; resp[1] <= 8'h01;
                                    resp[2] <= 8'd0; resp[3] <= {3'd0, state};
                                    resp[4] <= CMD_PROGRAM16; resp[5] <= 8'd0;
                                    resp[6] <= 8'd0; resp[7] <= {5'd0, spi_op};
                                    resp_len<=5'd8; resp_idx<=5'd0; resp_crc_pending <= CAPS0[7];
                                    last_err_code<=8'h01; last_err_cmd<=CMD_PROGRAM16;
                                    last_err_detail<=8'd0; last_err_valid<=1'b1;
                                    err_count<=err_count+16'd1; state<=S_TX_RESP;
                                end else begin
                                    spi_op<=3'd5; spi_addr<={rxb[4],rxb[5],rxb[6]};
                                    spi_prog_data<={rxb[7],rxb[8],rxb[9],rxb[10],rxb[11],rxb[12],rxb[13],rxb[14],rxb[15],rxb[16],rxb[17],rxb[18],rxb[19],rxb[20],rxb[21],rxb[22]};
                                    spi_start<=1'b1; spi_done_latch<=1'b0; spi_ok_latch<=1'b0;
                                    prog_count<=prog_count+16'd1; state<=S_WAIT_SPI;
                                end
                            end
                            CMD_SDRAM_READ16: begin
                                raw_active <= 1'b1;
                                raw_wr <= 1'b0;
                                raw_addr <= {rxb[0], rxb[1], rxb[2]};
                                raw_word_idx <= 3'd0;
                                raw_rdata_buf <= 128'd0;
                                state <= S_RAW_READ_LOOP;
                            end
                            CMD_SDRAM_WRITE16: begin
                                sdram_wr <= 1'b1;
                                sdram_base_addr <= {rxb[0], rxb[1], rxb[2]};
                                sdram_wdata <= {
                                    rxb[3],  rxb[4],  rxb[5],  rxb[6],
                                    rxb[7],  rxb[8],  rxb[9],  rxb[10],
                                    rxb[11], rxb[12], rxb[13], rxb[14],
                                    rxb[15], rxb[16], rxb[17], rxb[18]
                                };
                                sdram_start <= 1'b1; sdram_done_latch <= 1'b0;
                                state <= S_WAIT_SDRAM;
                            end
                            CMD_SDRAM_WRITE_STREAM: begin
                                stream_addr <= {rxb[0], rxb[1], rxb[2]};
                                stream_remaining <= {rxb[3], rxb[4]};
                                stream_byte_idx <= 4'd0;
                                stream_idle_cnt <= STREAM_TIMEOUT;
                                state <= S_SDRAM_STREAM;
                            end
                            CMD_SDRAM_TO_FLASH: begin
                                loop_flash_addr <= {rxb[0], rxb[1], rxb[2]};
                                loop_remaining  <= {rxb[3], rxb[4], rxb[5]};
                                loop_sdram_word <= 24'd0;
                                loop_phase <= 2'd0;
                                state <= S_SDRAM_FLASH_LOOP;
                            end
                            CMD_SDRAM_VERIFY_FLASH: begin
                                loop_flash_addr <= {rxb[0], rxb[1], rxb[2]};
                                loop_remaining  <= {rxb[3], rxb[4], rxb[5]};
                                loop_sdram_word <= 24'd0;
                                loop_phase <= 2'd0;
                                state <= S_SDRAM_VERIFY;
                            end
                            CMD_RAW_WRITE: begin
                                raw_active <= 1'b1;
                                raw_req <= 1'b1; raw_wr <= 1'b1;
                                raw_addr <= {rxb[0], rxb[1], rxb[2]};
                                raw_wdata <= {rxb[3], rxb[4]};
                                state <= S_RAW_WAIT_ACK;
                            end
                            CMD_RAW_READ: begin
                                raw_active <= 1'b1;
                                raw_req <= 1'b1; raw_wr <= 1'b0;
                                raw_addr <= {rxb[0], rxb[1], rxb[2]};
                                raw_wdata <= 16'd0;
                                state <= S_RAW_WAIT_ACK;
                            end
                            CMD_SD_READ16: begin
                                sd_op <= 3'd2;
                                sd_lba <= {rxb[0], rxb[1], rxb[2], rxb[3]};
                                sd_chunk_idx <= rxb[4][4:0];
                                sd_start <= 1'b1; sd_done_latch <= 1'b0; sd_ok_latch <= 1'b0;
                                state <= S_WAIT_SD;
                            end
                            CMD_SD_CRC32: begin
                                sd_op <= 3'd3;
                                sd_lba <= {rxb[0], rxb[1], rxb[2], rxb[3]};
                                sd_start <= 1'b1; sd_done_latch <= 1'b0; sd_ok_latch <= 1'b0;
                                state <= S_WAIT_SD;
                            end
                            CMD_SD_WRITE512: begin
                                sd_lba <= {rxb[0], rxb[1], rxb[2], rxb[3]};
                                didx <= 10'd0;
                                stream_idle_cnt <= STREAM_TIMEOUT;
                                state <= S_SD_WRITE_RX;
                            end
                            CMD_SD_INSTALL: begin
                                // Cure list item #19. Latch the LBA, raise install_active
                                // (top.sv mux now routes flash + SD to the install engine),
                                // pulse install_start for one cycle, wait in S_WAIT_INSTALL
                                // for install_done. The engine reads the bundle header from
                                // SD, validates magic, erases each 64 KiB sector at
                                // the bundle's target_address, then programs the payload.
                                install_lba    <= {rxb[0], rxb[1], rxb[2], rxb[3]};
                                install_active <= 1'b1;
                                install_start  <= 1'b1;
                                state <= S_WAIT_INSTALL;
                            end
                            CMD_SD_CRC32_RANGE: begin
                                crc_range_start <= 1'b1;
                                crc_range_lba   <= {rxb[0], rxb[1], rxb[2], rxb[3]};
                                crc_range_count <= {rxb[4], rxb[5]};
                                state <= S_WAIT_SD;
                            end
                            CMD_SET_WATCHDOG: begin
                                watchdog_set_pulse <= 1'b1;
                                watchdog_set_value <= {rxb[0], rxb[1], rxb[2], rxb[3]};
                                resp[0] <= CMD_SET_WATCHDOG; resp[1] <= ACK;
                                resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                            end
                            CMD_UNLOCK: begin
                                // UNLOCK retained as a benign no-op for backwards
                                // compatibility with hosts that still call it.
                                // The new inline-key protocol makes the flag
                                // unnecessary; ACK so old hosts don't error.
                                resp[0] <= CMD_UNLOCK; resp[1] <= ACK;
                                resp_len <= 5'd2; resp_idx <= 5'd0; resp_crc_pending <= CAPS0[7]; state <= S_TX_RESP;
                            end
                            default: state <= S_IDLE;
                        endcase
                    end
                end

                // Flash subsystem states (extracted to rime_svc_flash.svh)
                `include "rime_svc_flash.svh"

                // SDRAM subsystem states (extracted to rime_svc_sdram.svh)
                `include "rime_svc_sdram.svh"

                // SD subsystem states (extracted to rime_svc_sd.svh)
                `include "rime_svc_sd.svh"

                // --- placeholder to prevent dangling else (removed states follow) ---
                // The states below were inlined here before extraction.
                // S_WAIT_SD, S_SD_WRITE_RX, S_WAIT_INSTALL are now in rime_svc_sd.svh.
                // S_WAIT_SDRAM, S_RAW_*, S_SDRAM_STREAM/FLASH_LOOP/VERIFY are now in rime_svc_sdram.svh.
                // S_WAIT_SPI is now in rime_svc_flash.svh.
                5'd31: begin  // unreachable sentinel — keeps the case block well-formed
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
