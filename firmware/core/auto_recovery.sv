// auto_recovery: boot-time autonomous SD-to-flash recovery FSM.
//
// Runs on every FPGA boot. Initializes SD, reads a 64-byte control
// block from LBA 1, validates magic/checksum/armed flag, and
// if armed, starts the sd_install_engine to install the primary bundle.
// Any UART byte received during recovery aborts immediately — the
// operator is never locked out.
//
// Control block format (64 bytes at SD LBA 1, little-endian):
//   [0:7]   magic     "RIMEAUTO"
//   [8:11]  reserved
//   [12:15] flags     bit 0 = armed
//   [16:19] primary_lba  — bundle location on SD
//   [20:59] reserved
//   [60:63] checksum  — sum of all preceding 32-bit words
//
// The hold output stays high until recovery completes (any path).
// While hold=1, the SD bus mux in top.sv routes SD commands from
// this module instead of rime_service.
//
// Exit reasons (output on exit_reason):
//   1 — success (install completed)
//   2 — SD init failed (no card or card error)
//   3 — install engine failed (detail = install error code)
//   4 — control block read failed
//   5 — control block invalid (detail: 0x01=magic, 0x03=checksum)
//   6 — not armed
//   7 — aborted by UART activity or no bundle

module auto_recovery (
    input  wire        clk,
    input  wire        rst,

    input  wire        uart_rx_activity,
    output logic       hold,
    output logic [2:0] exit_reason,
    output logic [7:0] exit_detail,

    output logic        install_start,
    output logic [31:0] install_lba,
    input  wire         install_busy,
    input  wire         install_done,
    input  wire         install_ok,
    input  wire  [7:0]  install_error,

    output logic        sd_start,
    output logic [2:0]  sd_op,
    output logic [31:0] sd_lba,
    output logic [4:0]  sd_chunk_idx,
    input  wire         sd_done,
    input  wire         sd_ok,
    input  wire [127:0] sd_read_data,

    output logic [8:0]  sd_load_addr,
    output logic [7:0]  sd_load_data,
    output logic        sd_load_en,
    output logic        sd_write_start,
    input  wire         sd_write_done
);

    localparam [3:0] S_IDLE         = 4'd0;
    localparam [3:0] S_SD_INIT      = 4'd1;
    localparam [3:0] S_WAIT_INIT    = 4'd2;
    localparam [3:0] S_POST_INIT    = 4'd9;
    localparam [3:0] S_READ_CTRL    = 4'd3;
    localparam [3:0] S_WAIT_CTRL    = 4'd4;
    localparam [3:0] S_VALIDATE     = 4'd5;
    localparam [3:0] S_INSTALL      = 4'd6;
    localparam [3:0] S_WAIT_INSTALL = 4'd7;
    localparam [3:0] S_DONE         = 4'd8;

    localparam [63:0] AUTO_MAGIC = 64'h52494D454155544F;  // "RIMEAUTO"
    localparam [31:0] CTRL_LBA = 32'd1;  // control block lives at SD block 1

    logic [3:0] state;
    logic [14:0] settle_cnt;  // post-init delay counter

    // Control block is read as four 16-byte SD chunks (64 bytes total).
    // ctrl0 holds bytes 0-15, ctrl1 holds 16-31, etc.
    logic [127:0] ctrl0, ctrl1, ctrl2, ctrl3;
    logic [1:0]   ctrl_idx;  // which chunk we're reading (0-3)
    logic          sd_done_l;

    // Extract a little-endian 32-bit word from a 128-bit chunk at byte offset.
    // The SD read returns bytes in big-endian order within the 128-bit register,
    // so this function reverses the byte order for the target 4-byte field.
    function automatic [31:0] le32(input [127:0] chunk, input integer byte_off);
        le32 = {chunk[(15-byte_off-3)*8 +: 8],
                chunk[(15-byte_off-2)*8 +: 8],
                chunk[(15-byte_off-1)*8 +: 8],
                chunk[(15-byte_off  )*8 +: 8]};
    endfunction

    // Decode control block fields from the four chunks
    wire [63:0]  ctrl_magic   = ctrl0[127:64];        // bytes 0-7: "RIMEAUTO"
    wire [31:0]  ctrl_flags   = le32(ctrl0, 12);       // bytes 12-15, bit 0 = armed
    wire [31:0]  ctrl_primary = le32(ctrl1, 0);
    wire         ctrl_armed   = ctrl_flags[0];

    wire [31:0] ctrl_checksum_stored = le32(ctrl3, 12);

    wire [31:0] cs_w0 = le32(ctrl0, 0);
    wire [31:0] cs_w1 = le32(ctrl0, 4);
    wire [31:0] cs_w2 = le32(ctrl0, 8);
    wire [31:0] cs_w3 = le32(ctrl0, 12);
    wire [31:0] cs_w4 = le32(ctrl1, 0);
    wire [31:0] cs_w5 = le32(ctrl1, 4);
    wire [31:0] cs_w6 = le32(ctrl1, 8);
    wire [31:0] cs_w7 = le32(ctrl1, 12);
    wire [31:0] cs_w8 = le32(ctrl2, 0);
    wire [31:0] cs_w9 = le32(ctrl2, 4);
    wire [31:0] cs_wA = le32(ctrl2, 8);
    wire [31:0] cs_wB = le32(ctrl2, 12);
    wire [31:0] cs_wC = le32(ctrl3, 0);
    wire [31:0] cs_wD = le32(ctrl3, 4);
    wire [31:0] cs_wE = le32(ctrl3, 8);

    wire [31:0] checksum_computed = cs_w0 + cs_w1 + cs_w2 + cs_w3 +
                                    cs_w4 + cs_w5 + cs_w6 + cs_w7 +
                                    cs_w8 + cs_w9 + cs_wA + cs_wB +
                                    cs_wC + cs_wD + cs_wE;

    always_ff @(posedge clk) begin
        sd_start      <= 1'b0;
        install_start <= 1'b0;
        sd_load_en    <= 1'b0;
        sd_load_addr  <= 9'd0;
        sd_load_data  <= 8'd0;
        sd_write_start <= 1'b0;

        // Done-latch with start-clears-first priority. The else-if prevents
        // a stale sd_done=1 from a previous operation from immediately
        // re-latching on the same cycle as a new sd_start pulse.
        if (sd_start)
            sd_done_l <= 1'b0;
        else if (sd_done)
            sd_done_l <= 1'b1;

        if (rst) begin
            state       <= S_IDLE;
            hold        <= 1'b1;
            exit_reason <= 3'd0;
            exit_detail <= 8'd0;
            sd_done_l   <= 1'b0;
        end else case (state)

            S_IDLE: begin
                hold     <= 1'b1;
                ctrl_idx <= 2'd0;
                state    <= S_SD_INIT;
            end

            S_SD_INIT: begin
                sd_op     <= 3'd1;
                sd_lba    <= 32'd0;
                sd_start  <= 1'b1;
                sd_done_l <= 1'b0;
                state     <= S_WAIT_INIT;
            end

            S_WAIT_INIT: begin
                if (uart_rx_activity) begin
                    exit_reason <= 3'd7;
                    state <= S_DONE;
                end else if (sd_done_l) begin
                    if (!sd_ok) begin
                        exit_reason <= 3'd2;
                        state <= S_DONE;
                    end else begin
                        settle_cnt <= 15'd0;
                        state <= S_POST_INIT;
                    end
                end
            end

            S_POST_INIT: begin
                if (uart_rx_activity) begin
                    exit_reason <= 3'd7;
                    state <= S_DONE;
                end else if (settle_cnt >= 15'd25000) begin
                    state <= S_READ_CTRL;
                end else begin
                    settle_cnt <= settle_cnt + 15'd1;
                end
            end

            S_READ_CTRL: begin
                if (uart_rx_activity) begin
                    exit_reason <= 3'd7;
                    state <= S_DONE;
                end else begin
                    sd_op        <= 3'd2;
                    sd_lba       <= CTRL_LBA;
                    sd_chunk_idx <= {3'd0, ctrl_idx};
                    sd_start     <= 1'b1;
                    sd_done_l    <= 1'b0;
                    state        <= S_WAIT_CTRL;
                end
            end

            S_WAIT_CTRL: begin
                if (uart_rx_activity) begin
                    exit_reason <= 3'd7;
                    state <= S_DONE;
                end else if (sd_done_l) begin
                    if (!sd_ok) begin
                        exit_reason <= 3'd4;
                        state <= S_DONE;
                    end else begin
                        case (ctrl_idx)
                            2'd0: ctrl0 <= sd_read_data;
                            2'd1: ctrl1 <= sd_read_data;
                            2'd2: ctrl2 <= sd_read_data;
                            2'd3: ctrl3 <= sd_read_data;
                        endcase
                        if (ctrl_idx == 2'd3)
                            state <= S_VALIDATE;
                        else begin
                            ctrl_idx <= ctrl_idx + 2'd1;
                            state    <= S_READ_CTRL;
                        end
                    end
                end
            end

            S_VALIDATE: begin
                if (uart_rx_activity) begin
                    exit_reason <= 3'd7;
                    state <= S_DONE;
                end else if (ctrl_magic != AUTO_MAGIC) begin
                    exit_reason <= 3'd5;
                    exit_detail <= 8'h01;
                    state <= S_DONE;
                end else if (ctrl_checksum_stored != checksum_computed) begin
                    exit_reason <= 3'd5;
                    exit_detail <= 8'h03;
                    state <= S_DONE;
                end else if (!ctrl_armed) begin
                    exit_reason <= 3'd6;
                    state <= S_DONE;
                end else if (ctrl_primary == 32'd0) begin
                    exit_reason <= 3'd7;
                    state <= S_DONE;
                end else begin
                    install_lba   <= ctrl_primary;
                    install_start <= 1'b1;
                    state         <= S_WAIT_INSTALL;
                end
            end

            S_WAIT_INSTALL: begin
                if (uart_rx_activity && !install_busy) begin
                    exit_reason <= 3'd7;
                    state <= S_DONE;
                end else if (install_done) begin
                    if (install_ok)
                        exit_reason <= 3'd1;
                    else begin
                        exit_reason <= 3'd3;
                        exit_detail <= install_error;
                    end
                    state <= S_DONE;
                end
            end

            S_DONE: begin
                hold <= 1'b0;
                state <= S_DONE;
            end

            default: begin
                hold <= 1'b0;
                state <= S_DONE;
            end
        endcase
    end
endmodule
