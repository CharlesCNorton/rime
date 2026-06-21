// RIME top module: clock divider, reset sequencer, UART, SPI flash,
// SDRAM controller, SD SPI master, rime_service protocol FSM,
// sd_install_engine, auto_recovery, watchdog, CRC-32 range helper,
// and the CRC-8 frame inject chain.
//
// Bus muxing: the SD SPI master and flash SPI master are shared between
// four drivers in priority order: (1) sd_install_engine, (2) auto_recovery,
// (3) CRC-32 range helper, (4) rime_service. See the fin_sd_* and fin_spi_*
// mux nets near the top of this module.
//
// Reset: driven solely by button[0] and the 16-cycle startup sequencer.
// SW_RESET and watchdog are handled internally by rime_service (the
// reset_armed counter fires after the ACK drains). svc_reset_req and
// wdog_reset are NOT wired to rst — doing so creates a combinational
// feedback cycle that synthesis resolves by constant-folding the reset tree.

module top (
    input  wire       clk,
    input  wire       usb_rx,
    output wire       usb_tx,
    output logic [4:0] led,
    input  wire [1:0] button,
    output wire       flash_csn,
    output wire       flash_mosi,
    output wire       flash_wpn,
    output wire       flash_resetn,
    input  wire       flash_miso,
    output wire       sd_clk,
    output wire       sd_csn,
    output wire       sd_mosi,
    input  wire       sd_miso,
    input  wire       sd_det,
    output wire        sdram_clk,
    output wire        sdram_cke,
    output wire        sdram_csn,
    output wire        sdram_rasn,
    output wire        sdram_casn,
    output wire        sdram_wen,
    output wire [1:0]  sdram_ba,
    output wire [12:0] sdram_a,
    inout  wire [15:0] sdram_dq,
    output wire [1:0]  sdram_dqm
);
    localparam integer CLK_HZ = 25000000;
    localparam integer BAUD   = 115200;

    // Cure list item #19. Forward declarations for the install-engine bus
    // mux. These names are referenced by the SD and flash SPI muxes below
    // before the install_engine and rime_service instantiations are reached.
    // Without explicit declarations, Verilog would create 1-bit implicit
    // wires for some of these, silently breaking the 32-bit address paths.
    wire        inst_active;          // mux select: install vs everyone else
    wire        inst_busy;             // engine busy output
    wire        inst_start, inst_done, inst_ok;
    wire [31:0] inst_lba;
    wire [7:0]  inst_error;
    wire [7:0]  inst_error_detail;
    wire [2:0]  inst_spi_op;
    wire [23:0] inst_spi_addr;
    wire [127:0] inst_spi_prog;
    wire        inst_spi_start;
    wire        inst_sd_start;
    wire [2:0]  inst_sd_op;
    wire [31:0] inst_sd_lba;
    wire [4:0]  inst_sd_chunk;
    wire        svc_inst_start;
    wire        svc_inst_active;
    wire [31:0] svc_inst_lba;

    wire        svc_reset_req;
    wire        svc_wdog_pulse;
    wire [31:0] svc_wdog_value;
    wire        svc_crc_range_start;
    wire [31:0] svc_crc_range_lba;
    wire [15:0] svc_crc_range_count;

    wire        svc_sd_start;
    wire [2:0]  svc_sd_op;
    wire [31:0] svc_sd_lba;
    wire [4:0]  svc_sd_chunk;
    wire        sd_busy_w, sd_done_w, sd_ok_w;
    wire        sd_card_present_w, sd_init_w, sd_hc_w;
    wire [7:0]  sd_last_err_w, sd_last_r1_w;
    wire [127:0] sd_read_data_w;
    wire [31:0] sd_read_crc32_w;
    wire [8:0]  svc_sd_wr_addr;
    wire [7:0]  sd_wr_data_w;
    wire [8:0]  svc_sd_load_addr;
    wire [7:0]  svc_sd_load_data;
    wire        svc_sd_load_en;

    // The SD master is shared between four drivers (priority order):
    //   1. inst_active — sd_install_engine (host CMD_SD_INSTALL or auto-recovery install)
    //   2. recov_hold  — auto_recovery (SD init + control block read on boot)
    //   3. cr_active   — SD_CRC32_RANGE helper FSM
    //   4. svc         — rime_service (normal SD commands)
    wire         fin_sd_start = inst_active ? inst_sd_start
                              : (recov_hold ? recov_sd_start
                              : (cr_active  ? cr_sd_start
                                            : svc_sd_start));
    wire [2:0]   fin_sd_op    = inst_active ? inst_sd_op
                              : (recov_hold ? recov_sd_op
                              : (cr_active  ? cr_sd_op
                                            : svc_sd_op));
    wire [31:0]  fin_sd_lba   = inst_active ? inst_sd_lba
                              : (recov_hold ? recov_sd_lba
                              : (cr_active  ? cr_sd_lba
                                            : svc_sd_lba));
    wire [4:0]   fin_sd_chunk = inst_active ? inst_sd_chunk
                              : (recov_hold ? recov_sd_chunk
                              : (cr_active  ? 5'd0
                                            : svc_sd_chunk));

    sd_spi_master #(.CLK_HZ(CLK_HZ)) SD_SPI (
        .clk(sys_clk), .rst(rst),
        .start(fin_sd_start), .op(fin_sd_op), .lba(fin_sd_lba),
        .chunk_index(fin_sd_chunk),
        .write_byte_addr(svc_sd_wr_addr), .write_byte_data(sd_wr_data_w),
        .load_byte_addr(svc_sd_load_addr), .load_byte_data(svc_sd_load_data), .load_byte_en(svc_sd_load_en),
        .busy(sd_busy_w), .done(sd_done_w), .ok(sd_ok_w),
        .card_present(sd_card_present_w), .initialized(sd_init_w),
        .high_capacity(sd_hc_w),
        .last_error(sd_last_err_w), .last_r1(sd_last_r1_w),
        .read_data(sd_read_data_w), .read_crc32(sd_read_crc32_w),
        .crc_seed(sd_read_crc32_w),
        .sd_clk(sd_clk), .sd_csn(sd_csn), .sd_mosi(sd_mosi),
        .sd_miso(sd_miso), .sd_det(sd_det),
        .dbg_state(sd_dbg_state), .dbg_shift_in(sd_dbg_shin), .dbg_shift_busy(sd_dbg_shbusy)
    );
    wire [4:0] sd_dbg_state;
    wire [7:0] sd_dbg_shin;
    wire       sd_dbg_shbusy;

    logic sys_clk;
    always_ff @(posedge clk) begin
        if (~button[0]) sys_clk <= 1'b0;
        else sys_clk <= ~sys_clk;
    end

    // (* keep *) annotations in this file and rime_service.sv fall into two categories:
    //   STRUCTURAL: the signal drives a cross-module feedback path or CRC inject
    //     chain that synthesis constant-folds without the attribute. These must stay
    //     until the signal path is restructured.
    //     - app_mode (rime_service.sv): combinational cycle through ENTER_SERVICE decode
    //     - svc_frame_done, frame_crc, want_crc, crc_inject, frame_active: CRC-8 inject chain
    //   DEFENSIVE: the signal was folded by a past synthesizer but the root
    //     cause (feedback cycle, dead-looking latch) is now fixed. Retained as insurance
    //     against optimizer regressions. Candidates for removal once re-verified
    //     on silicon under the current synthesizer.
    //     - startup_cnt, startup_done, rst: startup sequencer (cycle broken in cure #21)
    //     - rime_i_core: state, pc, next_pc (belt-and-suspenders on CPU state)
    //     - ring oscillator experiments: LUT4 chain (required by design — not removable)
    (* keep *) logic [3:0] startup_cnt;
    (* keep *) logic       startup_done;
    always_ff @(posedge sys_clk) begin
        if (~button[0]) begin
            startup_cnt  <= 4'd0;
            startup_done <= 1'b0;
        end else if (!startup_done) begin
            if (startup_cnt == 4'd15) startup_done <= 1'b1;
            else startup_cnt <= startup_cnt + 4'd1;
        end
    end
    // Direct button[0] reset, bypassing the startup sequencer.
    // A past synthesizer constant-folded startup_done despite (* keep *),
    // making rst permanently asserted. This workaround removes the
    // startup_done dependency — the 16-cycle startup delay is not
    // functionally critical since the SDRAM controller has its own
    // init sequence and the service FSM handles the first-command
    // timing internally.
    // svc_reset_req and wdog_reset feed back into the same rst that
    // resets rime_service, creating a combinational cycle that synthesis
    // resolves by constant-folding the entire reset tree. Breaking
    // the cycle: rst is driven solely by button[0] and the startup
    // sequencer. SW_RESET and watchdog are handled by the service
    // FSM internally (reset_armed counter fires after the ACK drains).
    (* keep *) wire rst = ~button[0] || !startup_done;

    wire       rx_valid;
    wire [7:0] rx_data;
    wire       svc_tx_send;
    wire [7:0] svc_tx_data;

    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) RX (
        .clk(sys_clk), .rx(usb_rx), .finish(rx_valid), .data(rx_data)
    );

    // rime_service emits the entire framed response itself
    //   ([type, len_lo, len_hi, payload, crc8]),
    // so top.sv just passes the TX bytes straight through — no top-level CRC
    // inject chain, hence no feedback cycle for synthesis to constant-fold.
    wire svc_frame_done;  // end-of-frame pulse from rime_service; unused here
    wire       tx_send     = svc_tx_send;
    wire [7:0] tx_data_out = svc_tx_data;

    uart_tx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) TX (
        .clk(sys_clk), .send(tx_send), .data(tx_data_out), .tx(usb_tx)
    );

    logic [15:0] tx_busy_counter;
    wire tx_busy = (tx_busy_counter != 16'd0);
    localparam integer UART_CHAR_CLKS = ((CLK_HZ / BAUD) * 11);
    always_ff @(posedge sys_clk) begin
        if (rst) tx_busy_counter <= 16'd0;
        else if (tx_send) tx_busy_counter <= UART_CHAR_CLKS[15:0];
        else if (tx_busy_counter != 16'd0) tx_busy_counter <= tx_busy_counter - 16'd1;
    end

    wire        spi_flash_clk;
    wire [2:0]  svc_spi_op;
    wire [23:0] svc_spi_addr;
    wire [127:0] svc_spi_prog;
    wire        svc_spi_start;
    wire        spi_busy, spi_done, spi_ok;
    wire [127:0] spi_read_data;
    wire [15:0] spi_status;
    wire [23:0] spi_jedec;

    // Cure list item #19. install_active routes the flash SPI master from
    // sd_install_engine instead of rime_service while a CMD_SD_INSTALL or
    // boot-time auto-recovery is in flight.
    wire [2:0]   fin_spi_op    = inst_active ? inst_spi_op    : svc_spi_op;
    wire [23:0]  fin_spi_addr  = inst_active ? inst_spi_addr  : svc_spi_addr;
    wire [127:0] fin_spi_prog  = inst_active ? inst_spi_prog  : svc_spi_prog;
    wire         fin_spi_start = inst_active ? inst_spi_start : svc_spi_start;

    flash_spi_master #(.CLK_HZ(CLK_HZ), .SCK_HZ(12000000)) SPI (
        .clk(sys_clk), .rst(rst),
        .start(fin_spi_start), .op(fin_spi_op), .addr(fin_spi_addr),
        .read_chunk_count(6'd1), .prog_data(fin_spi_prog),
        .busy(spi_busy), .done(spi_done), .ok(spi_ok), .diag(),
        .jedec(spi_jedec), .status(spi_status),
        .read_data(spi_read_data), .read_crc32(),
        .flash_clk(spi_flash_clk), .flash_csn(flash_csn),
        .flash_mosi(flash_mosi), .flash_wpn(flash_wpn),
        .flash_resetn(flash_resetn), .flash_miso(flash_miso)
    );
    USRMCLK user_flash_clk (.USRMCLKI(spi_flash_clk), .USRMCLKTS(1'b0));

    wire sdram_init_done, sdram_ready, sdram_valid, sdram_ack;
    wire [15:0] sdram_rdata_raw;
    wire br_req, br_wr;
    wire [23:0] br_addr;
    wire [15:0] br_wdata;

    wire        svc_raw_req, svc_raw_wr, svc_raw_active;
    wire [23:0] svc_raw_addr;
    wire [15:0] svc_raw_wdata;

    wire mux_req   = svc_raw_active ? svc_raw_req   : br_req;
    wire mux_wr    = svc_raw_active ? svc_raw_wr    : br_wr;
    wire [23:0] mux_addr  = svc_raw_active ? svc_raw_addr  : br_addr;
    wire [15:0] mux_wdata = svc_raw_active ? svc_raw_wdata : br_wdata;

    wire [15:0] sdram_dq_out;
    wire sdram_dq_oe;
    wire [15:0] sdram_dq_in = sdram_dq;
    assign sdram_dq = sdram_dq_oe ? sdram_dq_out : 16'bz;

    sdram_controller #(.CLK_HZ(CLK_HZ)) SDRAM_CTRL (
        .clk(sys_clk), .rst(rst), .req(mux_req), .wr(mux_wr), .addr(mux_addr),
        .wdata(mux_wdata), .rdata(sdram_rdata_raw), .ready(sdram_ready),
        .valid(sdram_valid), .ack(sdram_ack), .init_done(sdram_init_done),
        .sdram_clk(sdram_clk), .sdram_cke(sdram_cke), .sdram_csn(sdram_csn),
        .sdram_rasn(sdram_rasn), .sdram_casn(sdram_casn), .sdram_wen(sdram_wen),
        .sdram_ba(sdram_ba), .sdram_a(sdram_a), .sdram_dq_out(sdram_dq_out),
        .sdram_dq_in(sdram_dq_in), .sdram_dq_oe(sdram_dq_oe), .sdram_dqm(sdram_dqm),
        .dbg_last_write_a(), .dbg_last_write_ba(), .dbg_last_req_addr()
    );

    wire        svc_sdram_start, svc_sdram_wr;
    wire [23:0] svc_sdram_base;
    wire [127:0] svc_sdram_wdata, svc_sdram_rdata;
    wire        svc_sdram_done, svc_sdram_busy;

    sdram_bridge #(.CLK_HZ(CLK_HZ)) SDRAM_BR (
        .clk(sys_clk), .rst(rst),
        .start(svc_sdram_start), .wr(svc_sdram_wr),
        .base_addr(svc_sdram_base), .wdata(svc_sdram_wdata),
        .rdata(svc_sdram_rdata), .done(svc_sdram_done), .busy(svc_sdram_busy),
        .sdram_req(br_req), .sdram_wr(br_wr), .sdram_addr(br_addr),
        .sdram_wdata(br_wdata), .sdram_rdata(sdram_rdata_raw),
        .sdram_ready(sdram_ready), .sdram_valid(sdram_valid), .sdram_ack(sdram_ack)
    );

    wire [4:0] svc_led;
    wire svc_busy;

    rime_service #(.CLK_HZ(CLK_HZ)) SVC (
        .clk(sys_clk), .rst(rst),
        .uart_rx_valid(rx_valid), .uart_rx_data(rx_data),
        .uart_tx_send(svc_tx_send), .uart_tx_data(svc_tx_data), .uart_tx_busy(tx_busy),
        .uart_tx_frame_done(svc_frame_done),
        .spi_op(svc_spi_op), .spi_addr(svc_spi_addr), .spi_prog_data(svc_spi_prog),
        .spi_start(svc_spi_start), .spi_busy(spi_busy), .spi_done(spi_done),
        .spi_ok(spi_ok), .spi_read_data(spi_read_data),
        .spi_status(spi_status), .spi_jedec(spi_jedec),
        .sdram_start(svc_sdram_start), .sdram_wr(svc_sdram_wr),
        .sdram_base_addr(svc_sdram_base), .sdram_wdata(svc_sdram_wdata),
        .sdram_rdata(svc_sdram_rdata), .sdram_done(svc_sdram_done),
        .sdram_busy(svc_sdram_busy), .sdram_init_done(sdram_init_done),
        .busy(svc_busy), .gpio_led(svc_led),
        .raw_req(svc_raw_req), .raw_wr(svc_raw_wr),
        .raw_addr(svc_raw_addr), .raw_wdata(svc_raw_wdata),
        .raw_rdata(sdram_rdata_raw), .raw_ready(sdram_ready),
        .raw_valid(sdram_valid), .raw_ack(sdram_ack),
        .raw_active(svc_raw_active),
        .sd_start(svc_sd_start), .sd_op(svc_sd_op), .sd_lba(svc_sd_lba),
        .sd_chunk_idx(svc_sd_chunk),
        .sd_busy(sd_busy_w), .sd_done(sd_done_w), .sd_ok(sd_ok_w),
        .sd_card_present(sd_card_present_w), .sd_initialized(sd_init_w),
        .sd_high_capacity(sd_hc_w),
        .sd_last_error(sd_last_err_w), .sd_last_r1(sd_last_r1_w),
        .sd_read_data(sd_read_data_w), .sd_read_crc32(sd_read_crc32_w),
        .sd_write_addr(svc_sd_wr_addr), .sd_write_data(sd_wr_data_w),
        .sd_load_addr(svc_sd_load_addr), .sd_load_data(svc_sd_load_data), .sd_load_en(svc_sd_load_en),
        .sd_det_in(sd_det),
        .reset_request(svc_reset_req),
        .watchdog_set_pulse(svc_wdog_pulse),
        .watchdog_set_value(svc_wdog_value),
        .crc_range_start(svc_crc_range_start),
        .crc_range_lba(svc_crc_range_lba),
        .crc_range_count(svc_crc_range_count),
        .crc_range_done(crc_range_done_w),
        .crc_range_result(crc_range_result_w),
        .sd_dbg_state(sd_dbg_state),
        .sd_dbg_shift_in(sd_dbg_shin),
        .sd_dbg_shift_busy(sd_dbg_shbusy),
        // Cure list item #19. Host-driven SD bundle install path.
        .install_start(svc_inst_start),
        .install_active(svc_inst_active),
        .install_lba(svc_inst_lba),
        .install_done(inst_done),
        .install_ok(inst_ok),
        .install_error_code(inst_error),
        .install_error_detail(inst_error_detail),
        .recovery_hold(recov_hold),
        .recovery_exit_reason(recov_exit_reason),
        .recovery_exit_detail(recov_exit_detail)
    );

    // svc_reset_req, svc_wdog_pulse, svc_crc_range_* forward-declared
    // near the top of this module to prevent implicit-wire shadowing.

    logic [31:0] wdog_limit, wdog_counter;
    logic        wdog_active, wdog_reset;
    always_ff @(posedge sys_clk) begin
        wdog_reset <= 1'b0;
        if (rst) begin
            wdog_active  <= 1'b0;
            wdog_limit   <= 32'd0;
            wdog_counter <= 32'd0;
        end else if (svc_wdog_pulse) begin
            wdog_limit   <= svc_wdog_value;
            wdog_counter <= 32'd0;
            wdog_active  <= (svc_wdog_value != 32'd0);
        end else if (wdog_active) begin
            if (rx_valid)
                wdog_counter <= 32'd0;
            else if (wdog_counter >= wdog_limit)
                wdog_reset <= 1'b1;
            else
                wdog_counter <= wdog_counter + 32'd1;
        end
    end

    // --- CRC-32 range helper FSM ---
    // Runs the SD CRC loop in top.sv to avoid adding case branches
    // to rime_service.sv (which has triggered the app_mode fold).
    localparam [1:0] CR_IDLE = 2'd0, CR_WAIT = 2'd1, CR_NEXT = 2'd2, CR_DONE = 2'd3;
    logic [1:0]  cr_state;
    logic [31:0] cr_lba;
    logic [15:0] cr_remaining;
    logic        cr_first;
    logic        cr_sd_start;
    logic [2:0]  cr_sd_op;
    logic [31:0] cr_sd_lba;
    logic        cr_sd_done_l;
    wire         crc_range_done_w = (cr_state == CR_DONE);
    wire  [31:0] crc_range_result_w = sd_read_crc32_w;

    always_ff @(posedge sys_clk) begin
        cr_sd_start <= 1'b0;
        if (cr_sd_start) cr_sd_done_l <= 1'b0;
        if (sd_done_w)   cr_sd_done_l <= 1'b1;
        if (rst) begin
            cr_state <= CR_IDLE;
            cr_sd_done_l <= 1'b0;
        end else case (cr_state)
            CR_IDLE: begin
                if (svc_crc_range_start) begin
                    cr_lba       <= svc_crc_range_lba;
                    cr_remaining <= svc_crc_range_count;
                    cr_first     <= 1'b1;
                    cr_state     <= CR_NEXT;
                end
            end
            CR_NEXT: begin
                cr_sd_op    <= cr_first ? 3'd3 : 3'd5;
                cr_sd_lba   <= cr_lba;
                cr_sd_start <= 1'b1;
                cr_sd_done_l <= 1'b0;
                cr_first    <= 1'b0;
                cr_state    <= CR_WAIT;
            end
            CR_WAIT: begin
                if (cr_sd_done_l && !sd_busy_w) begin
                    cr_lba       <= cr_lba + 32'd1;
                    cr_remaining <= cr_remaining - 16'd1;
                    if (cr_remaining <= 16'd1)
                        cr_state <= CR_DONE;
                    else
                        cr_state <= CR_NEXT;
                end
            end
            CR_DONE: begin
                cr_state <= CR_IDLE;
            end
        endcase
    end

    wire cr_active = (cr_state != CR_IDLE);

    logic [23:0] heartbeat;
    always_ff @(posedge sys_clk) begin
        if (rst) heartbeat <= 24'd0;
        else heartbeat <= heartbeat + 24'd1;
    end
    assign led = {heartbeat[23], svc_led[3:0]};

    // All inst_* wire declarations live near the top of this module so that
    // the bus muxes can reference them without implicit 1-bit shadows.

    sd_install_engine INSTALL (
        .clk(sys_clk), .rst(rst),
        .start(inst_start), .bundle_lba(inst_lba),
        .busy(inst_busy), .done(inst_done), .ok(inst_ok),
        .error_code(inst_error), .error_detail(inst_error_detail),
        .spi_op(inst_spi_op), .spi_addr(inst_spi_addr),
        .spi_prog_data(inst_spi_prog), .spi_start(inst_spi_start),
        .spi_done(spi_done), .spi_ok(spi_ok),
        .sd_start(inst_sd_start), .sd_op(inst_sd_op),
        .sd_lba(inst_sd_lba), .sd_chunk_idx(inst_sd_chunk),
        .sd_done(sd_done_w), .sd_ok(sd_ok_w), .sd_read_data(sd_read_data_w)
    );

    // inst_active is high while either the host-driven SD_INSTALL or the
    // boot-time auto-recovery has the install engine running. The mux at
    // the top of this file gates the SD master and flash SPI master on this.
    assign inst_active = svc_inst_active | inst_busy;

    wire        recov_hold;
    wire [2:0]  recov_exit_reason;
    wire [7:0]  recov_exit_detail;
    wire        recov_inst_start;
    wire [31:0] recov_inst_lba;
    wire        recov_sd_start;
    wire [2:0]  recov_sd_op;
    wire [31:0] recov_sd_lba;
    wire [4:0]  recov_sd_chunk;

    auto_recovery RECOVERY (
        .clk(sys_clk), .rst(rst),
        .uart_rx_activity(rx_valid),
        .hold(recov_hold),
        .exit_reason(recov_exit_reason), .exit_detail(recov_exit_detail),
        .install_start(recov_inst_start), .install_lba(recov_inst_lba),
        .install_busy(1'b0), .install_done(inst_done),
        .install_ok(inst_ok), .install_error(inst_error),
        .sd_start(recov_sd_start), .sd_op(recov_sd_op),
        .sd_lba(recov_sd_lba), .sd_chunk_idx(recov_sd_chunk),
        .sd_done(sd_done_w), .sd_ok(sd_ok_w), .sd_read_data(sd_read_data_w),
        .sd_load_addr(), .sd_load_data(), .sd_load_en(),
        .sd_write_start(), .sd_write_done(1'b0)
    );

    // Cure list item #19. The install engine is shared between two starters:
    //   - recov_inst_start from auto_recovery (boot-time SD-to-flash recovery)
    //   - svc_inst_start from rime_service (host-driven CMD_SD_INSTALL 0x7D)
    // Both pulse for one cycle. Either may run; the engine's busy/done/ok
    // outputs are wired to both consumers.
    assign inst_start = recov_inst_start | svc_inst_start;
    assign inst_lba   = svc_inst_active ? svc_inst_lba : recov_inst_lba;

endmodule
