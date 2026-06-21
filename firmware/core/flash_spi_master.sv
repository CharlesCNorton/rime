// flash_spi_master: QSPI NOR flash transaction engine for W25Q128.
//
// Handles JEDEC-ID read, status-register read, 16-byte page read,
// 64 KiB sector erase, 16-byte page program, and CRC-32 bulk read.
// Each operation is atomic: assert start with the desired op code,
// wait for done to pulse, read the result from the output registers.
//
// Operations (active on start pulse):
//   OP_JEDEC (1)     — read 3-byte JEDEC ID → jedec[23:0]
//   OP_STATUS (2)    — read SR1 + SR2 → status[15:0]
//   OP_READ16 (3)    — read 16 bytes at addr → read_data[127:0]
//   OP_ERASE64 (4)   — erase 64 KiB sector at addr, polls WIP until done
//   OP_PROGRAM16 (5) — page-program 16 bytes at addr from prog_data
//   OP_CRC32_16N (6) — streaming CRC-32 over N*16 bytes at addr → read_crc32
//
// The low-level SPI shift register runs at SCK_HZ (default 4 MHz init,
// 12 MHz operational). Write-enable (WREN) is issued automatically
// before erase and program operations. Erase/program poll SR1.WIP
// with configurable timeout limits.
//
// Parameters:
//   CLK_HZ — system clock frequency
//   SCK_HZ — SPI clock frequency (divided from CLK_HZ)

module flash_spi_master #(
    parameter integer CLK_HZ = 50000000,
    parameter integer SCK_HZ = 4000000
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         start,
    input  wire [2:0]   op,
    input  wire [23:0]  addr,
    input  wire [5:0]   read_chunk_count,
    input  wire [127:0] prog_data,
    output logic        busy,
    output logic        done,
    output logic        ok,
    output logic [7:0]  diag,
    output logic [23:0] jedec,
    output logic [15:0] status,
    output logic [127:0] read_data,
    output logic [31:0] read_crc32,
    output logic        flash_clk,
    output logic        flash_csn,
    output logic        flash_mosi,
    output logic        flash_wpn,
    output logic        flash_resetn,
    input  wire         flash_miso
);
    localparam [2:0] OP_NONE      = 3'd0;
    localparam [2:0] OP_JEDEC     = 3'd1;
    localparam [2:0] OP_STATUS    = 3'd2;
    localparam [2:0] OP_READ16    = 3'd3;
    localparam [2:0] OP_ERASE64   = 3'd4;
    localparam [2:0] OP_PROGRAM16 = 3'd5;
    localparam [2:0] OP_CRC32_16N = 3'd6;

    localparam [7:0] CMD_WREN   = 8'h06;
    localparam [7:0] CMD_READ   = 8'h03;
    localparam [7:0] CMD_PP     = 8'h02;
    localparam [7:0] CMD_SE64   = 8'hD8;
    localparam [7:0] CMD_JEDEC  = 8'h9F;
    localparam [7:0] CMD_RDSR1  = 8'h05;
    localparam [7:0] CMD_RDSR2  = 8'h35;

    localparam integer HALF_DIV = (CLK_HZ / (SCK_HZ * 2)) < 1 ? 1 : (CLK_HZ / (SCK_HZ * 2));
    localparam integer POLL_LIMIT_PROGRAM = 18'd20000;
    localparam integer POLL_LIMIT_ERASE = 18'd200000;

    localparam [2:0] TXN_DEST_NONE    = 3'd0;
    localparam [2:0] TXN_DEST_JEDEC   = 3'd1;
    localparam [2:0] TXN_DEST_STATUS1 = 3'd2;
    localparam [2:0] TXN_DEST_STATUS2 = 3'd3;
    localparam [2:0] TXN_DEST_READ    = 3'd4;
    localparam [2:0] TXN_DEST_READCRC = 3'd5;

    localparam [3:0] H_IDLE            = 4'd0;
    localparam [3:0] H_LAUNCH_JEDEC    = 4'd1;
    localparam [3:0] H_WAIT_JEDEC      = 4'd2;
    localparam [3:0] H_LAUNCH_STATUS1  = 4'd3;
    localparam [3:0] H_WAIT_STATUS1    = 4'd4;
    localparam [3:0] H_LAUNCH_STATUS2  = 4'd5;
    localparam [3:0] H_WAIT_STATUS2    = 4'd6;
    localparam [3:0] H_LAUNCH_READ     = 4'd7;
    localparam [3:0] H_WAIT_READ       = 4'd8;
    localparam [3:0] H_LAUNCH_WREN     = 4'd9;
    localparam [3:0] H_WAIT_WREN       = 4'd10;
    localparam [3:0] H_LAUNCH_WRITE    = 4'd11;
    localparam [3:0] H_WAIT_WRITE      = 4'd12;
    localparam [3:0] H_LAUNCH_POLL     = 4'd13;
    localparam [3:0] H_WAIT_POLL       = 4'd14;
    localparam [3:0] H_FINISH          = 4'd15;

    localparam [2:0] T_IDLE        = 3'd0;
    localparam [2:0] T_SEND_START  = 3'd1;
    localparam [2:0] T_SEND_WAIT   = 3'd2;
    localparam [2:0] T_READ_START  = 3'd3;
    localparam [2:0] T_READ_WAIT   = 3'd4;
    localparam [2:0] T_DEASSERT    = 3'd5;

    // Three nested levels: host FSM drives transactions, transaction FSM
    // drives byte shifts, shift register drives the SPI clock and data lines.

    // Host-level FSM: sequences multi-transaction flash operations
    logic [3:0]  host_state;
    logic [2:0]  txn_state;      // transaction-level FSM
    logic [2:0]  op_reg;         // latched operation from start pulse
    logic [23:0] addr_reg;       // latched 24-bit flash address
    logic [127:0] prog_reg;      // latched 16-byte program data
    logic [17:0] poll_count;     // WIP polling iteration counter

    // Transaction layer: one SPI CS-low session (send N bytes, read M bytes)
    logic [159:0] txn_bytes;     // outbound byte buffer (cmd + addr + data, up to 20 bytes)
    logic [127:0] txn_read_buf;  // inbound byte buffer
    logic [5:0] txn_len;         // bytes to send
    logic [9:0] txn_read_len;    // bytes to read after sending
    logic [5:0] txn_index;       // current send position
    logic [9:0] txn_read_index;  // current read position
    logic [2:0] txn_dest;        // where to route read data (JEDEC, STATUS, READ, CRC)
    logic       txn_start;       // pulse to begin a transaction
    logic       txn_done;        // pulse when transaction completes
    logic [31:0] txn_crc32;      // running CRC-32 for bulk read mode
    logic        crc_running;    // CRC bit-stepper active
    logic [2:0]  crc_step;       // CRC bit index (0-7 per byte)

    // SPI shift register: clocks one byte at SCK_HZ
    logic [7:0]  shift_rx;       // received byte (sampled on rising SCK edge)
    logic [7:0]  shift_tx;       // byte being transmitted
    logic [2:0]  shift_bit;      // current bit position (7 downto 0, MSB first)
    logic        shift_phase;    // 0 = rising edge (sample), 1 = falling edge (shift)
    logic [15:0] div_count;      // SCK half-period counter
    logic        shift_busy;
    logic        shift_done;     // pulses for one cycle when byte transfer completes
    logic        shift_start;
    logic [7:0]  shift_start_byte;

    assign diag = {shift_busy, start, txn_state, 1'b0, busy};

    integer i;

    always_ff @(posedge clk) begin
        shift_done <= 1'b0;
        txn_done   <= 1'b0;
        txn_start  <= 1'b0;
        shift_start <= 1'b0;
        done       <= 1'b0;

        if (rst) begin
            shift_busy <= 1'b0; shift_rx <= 8'h00; shift_tx <= 8'h00;
            shift_bit <= 3'd0; shift_phase <= 1'b0; div_count <= 16'd0;
            flash_clk <= 1'b0; flash_mosi <= 1'b0;
            txn_state <= T_IDLE; txn_index <= 6'd0; txn_read_index <= 10'd0;
            txn_crc32 <= 32'hFFFFFFFF; crc_running <= 1'b0; crc_step <= 3'd0;
            flash_csn <= 1'b1;
            busy <= 1'b0; ok <= 1'b0; host_state <= H_IDLE;
            op_reg <= OP_NONE; addr_reg <= 24'h0; prog_reg <= 128'h0;
            poll_count <= 18'd0; jedec <= 24'h0; status <= 16'h0;
            read_data <= 128'h0; read_crc32 <= 32'h0;
            flash_wpn <= 1'b1; flash_resetn <= 1'b1;
        end else begin

            // --- SPI shift register: one byte at a time, MSB first ---
            if (shift_start && !shift_busy) begin
                shift_busy <= 1'b1; shift_rx <= 8'h00;
                shift_tx <= shift_start_byte; shift_bit <= 3'd7;
                shift_phase <= 1'b0; div_count <= 16'd0;
                flash_clk <= 1'b0; flash_mosi <= shift_start_byte[7];
            end else if (shift_busy) begin
                if (div_count < (HALF_DIV - 1)) begin
                    div_count <= div_count + 16'd1;
                end else begin
                    div_count <= 16'd0;
                    if (!shift_phase) begin
                        // Rising SCK edge: sample MISO into the receive register
                        flash_clk <= 1'b1; shift_phase <= 1'b1;
                        shift_rx[shift_bit] <= flash_miso;
                    end else begin
                        // Falling SCK edge: advance to next bit or finish
                        flash_clk <= 1'b0; shift_phase <= 1'b0;
                        if (shift_bit == 3'd0) begin
                            shift_busy <= 1'b0; shift_done <= 1'b1;
                        end else begin
                            shift_bit <= shift_bit - 3'd1;
                            flash_mosi <= shift_tx[shift_bit - 3'd1];
                        end
                    end
                end
            end

            // CRC-32 bit stepper: processes one bit per cycle after a byte
            // is XOR'd into txn_crc32. Runs for 8 cycles (crc_step 0-7)
            // using the reflected IEEE 802.3 polynomial 0xEDB88320.
            if (crc_running) begin
                if (txn_crc32[0])
                    txn_crc32 <= (txn_crc32 >> 1) ^ 32'hEDB88320;
                else
                    txn_crc32 <= txn_crc32 >> 1;
                if (crc_step == 3'd7) crc_running <= 1'b0;
                else crc_step <= crc_step + 3'd1;
            end

            // --- Transaction FSM: one CS-low SPI session ---
            // Sends txn_len bytes from txn_bytes[], then reads txn_read_len
            // bytes, routing them to txn_read_buf or txn_crc32 based on txn_dest.
            case (txn_state)
                T_IDLE: begin
                    flash_csn <= 1'b1;  // CS deasserted between transactions
                    if (txn_start) begin
                        txn_index <= 6'd0; txn_read_index <= 10'd0;
                        txn_crc32 <= 32'hFFFFFFFF; crc_running <= 1'b0;
                        flash_csn <= 1'b0;  // assert CS
                        if (txn_len != 0) txn_state <= T_SEND_START;
                        else if (txn_read_len != 0) txn_state <= T_READ_START;
                        else txn_state <= T_DEASSERT;
                    end
                end
                T_SEND_START: begin
                    if (!shift_busy) begin
                        shift_start <= 1'b1;
                        shift_start_byte <= txn_bytes[(txn_index * 8) +: 8];
                        txn_state <= T_SEND_WAIT;
                    end
                end
                T_SEND_WAIT: begin
                    if (shift_done) begin
                        if ((txn_index + 6'd1) < txn_len) begin
                            txn_index <= txn_index + 6'd1;
                            txn_state <= T_SEND_START;
                        end else if (txn_read_len != 0) txn_state <= T_READ_START;
                        else txn_state <= T_DEASSERT;
                    end
                end
                T_READ_START: begin
                    if (!shift_busy) begin
                        // Clock out 0x00 to receive one byte from the flash
                        shift_start <= 1'b1; shift_start_byte <= 8'h00;
                        txn_state <= T_READ_WAIT;
                    end
                end
                T_READ_WAIT: begin
                    if (shift_done) begin
                        if (txn_dest == TXN_DEST_READCRC) begin
                            // CRC mode: XOR byte into accumulator, start 8-cycle bit stepper
                            txn_crc32 <= txn_crc32 ^ {24'd0, shift_rx};
                            crc_running <= 1'b1; crc_step <= 3'd0;
                        end else begin
                            txn_read_buf[(txn_read_index * 8) +: 8] <= shift_rx;
                        end
                        if ((txn_read_index + 6'd1) < txn_read_len) begin
                            txn_read_index <= txn_read_index + 6'd1;
                            txn_state <= T_READ_START;
                        end else txn_state <= T_DEASSERT;
                    end
                end
                T_DEASSERT: begin
                    // Wait for CRC bit-stepper to finish before signaling done,
                    // otherwise the host FSM reads a partially computed CRC.
                    flash_csn <= 1'b1;
                    if (!crc_running) begin
                        txn_done <= 1'b1;
                        txn_state <= T_IDLE;
                    end
                end
                default: txn_state <= T_IDLE;
            endcase

            flash_wpn <= 1'b1;
            flash_resetn <= 1'b1;

            // --- Host FSM: sequences flash operations as multi-transaction flows ---
            // JEDEC/STATUS/READ are single transactions. ERASE/PROGRAM require
            // WREN first, then the operation, then WIP polling until complete.
            case (host_state)
                H_IDLE: begin
                    busy <= 1'b0; ok <= 1'b0;
                    if (start) begin
                        busy <= 1'b1;
                        op_reg <= op; addr_reg <= addr; prog_reg <= prog_data;
                        poll_count <= 18'd0;
                        case (op)
                            OP_JEDEC:    host_state <= H_LAUNCH_JEDEC;
                            OP_STATUS:   host_state <= H_LAUNCH_STATUS1;
                            OP_READ16:   host_state <= H_LAUNCH_READ;
                            OP_CRC32_16N: host_state <= H_LAUNCH_READ;
                            OP_ERASE64,
                            OP_PROGRAM16: host_state <= H_LAUNCH_WREN;
                            default: begin busy <= 1'b0; done <= 1'b1; ok <= 1'b0; end
                        endcase
                    end
                end
                H_LAUNCH_JEDEC: begin
                    txn_len <= 6'd1; txn_read_len <= 6'd3;
                    txn_dest <= TXN_DEST_JEDEC; txn_bytes[7:0] <= CMD_JEDEC;
                    txn_start <= 1'b1; host_state <= H_WAIT_JEDEC;
                end
                H_WAIT_JEDEC: begin
                    if (txn_done) begin
                        jedec <= {txn_read_buf[7:0], txn_read_buf[15:8], txn_read_buf[23:16]};
                        ok <= 1'b1; done <= 1'b1; busy <= 1'b0;
                        host_state <= H_IDLE;
                    end
                end
                H_LAUNCH_STATUS1: begin
                    txn_len <= 6'd1; txn_read_len <= 6'd1;
                    txn_dest <= TXN_DEST_STATUS1; txn_bytes[7:0] <= CMD_RDSR1;
                    txn_start <= 1'b1; host_state <= H_WAIT_STATUS1;
                end
                H_WAIT_STATUS1: begin
                    if (txn_done) begin
                        status[7:0] <= txn_read_buf[7:0];
                        host_state <= H_LAUNCH_STATUS2;
                    end
                end
                H_LAUNCH_STATUS2: begin
                    txn_len <= 6'd1; txn_read_len <= 6'd1;
                    txn_dest <= TXN_DEST_STATUS2; txn_bytes[7:0] <= CMD_RDSR2;
                    txn_start <= 1'b1; host_state <= H_WAIT_STATUS2;
                end
                H_WAIT_STATUS2: begin
                    if (txn_done) begin
                        status[15:8] <= txn_read_buf[7:0];
                        ok <= 1'b1; done <= 1'b1; busy <= 1'b0;
                        host_state <= H_IDLE;
                    end
                end
                H_LAUNCH_READ: begin
                    txn_len <= 6'd4;
                    if (op_reg == OP_CRC32_16N) begin
                        txn_read_len <= {read_chunk_count, 4'b0000};
                        txn_dest <= TXN_DEST_READCRC;
                    end else begin
                        txn_read_len <= 10'd16;
                        txn_dest <= TXN_DEST_READ;
                    end
                    txn_bytes[7:0] <= CMD_READ;
                    txn_bytes[15:8] <= addr_reg[23:16];
                    txn_bytes[23:16] <= addr_reg[15:8];
                    txn_bytes[31:24] <= addr_reg[7:0];
                    txn_start <= 1'b1; host_state <= H_WAIT_READ;
                end
                H_WAIT_READ: begin
                    if (txn_done) begin
                        if (op_reg == OP_CRC32_16N) begin
                            read_crc32 <= ~txn_crc32;  // final complement per IEEE 802.3
                        end else begin
                            // Byte-reverse from shift-register order to big-endian
                            for (i = 0; i < 16; i = i + 1)
                                read_data[127 - (i * 8) -: 8] <= txn_read_buf[(i * 8) +: 8];
                        end
                        ok <= 1'b1; done <= 1'b1; busy <= 1'b0;
                        host_state <= H_FINISH;
                    end
                end
                H_FINISH: host_state <= H_IDLE;  // one-cycle gap before next op
                H_LAUNCH_WREN: begin
                    // W25Q128 requires WREN (0x06) before every erase or program
                    txn_len <= 6'd1; txn_read_len <= 6'd0;
                    txn_dest <= TXN_DEST_NONE; txn_bytes[7:0] <= CMD_WREN;
                    txn_start <= 1'b1; host_state <= H_WAIT_WREN;
                end
                H_WAIT_WREN: begin
                    if (txn_done) host_state <= H_LAUNCH_WRITE;
                end
                H_LAUNCH_WRITE: begin
                    if (op_reg == OP_ERASE64) begin
                        txn_len <= 6'd4; txn_read_len <= 6'd0; txn_dest <= TXN_DEST_NONE;
                        txn_bytes[7:0] <= CMD_SE64;
                        txn_bytes[15:8] <= addr_reg[23:16];
                        txn_bytes[23:16] <= addr_reg[15:8];
                        txn_bytes[31:24] <= addr_reg[7:0];
                    end else begin
                        txn_len <= 6'd20; txn_read_len <= 6'd0; txn_dest <= TXN_DEST_NONE;
                        txn_bytes[7:0] <= CMD_PP;
                        txn_bytes[15:8] <= addr_reg[23:16];
                        txn_bytes[23:16] <= addr_reg[15:8];
                        txn_bytes[31:24] <= addr_reg[7:0];
                        for (i = 0; i < 16; i = i + 1)
                            txn_bytes[((4 + i) * 8) +: 8] <= prog_reg[127 - (i * 8) -: 8];
                    end
                    txn_start <= 1'b1; host_state <= H_WAIT_WRITE;
                end
                H_WAIT_WRITE: begin
                    if (txn_done) begin poll_count <= 18'd0; host_state <= H_LAUNCH_POLL; end
                end
                H_LAUNCH_POLL: begin
                    // Poll SR1.WIP (bit 0) until the flash finishes the operation.
                    // Erase takes up to 400 ms; program up to 3 ms per page.
                    txn_len <= 6'd1; txn_read_len <= 6'd1;
                    txn_dest <= TXN_DEST_STATUS1; txn_bytes[7:0] <= CMD_RDSR1;
                    txn_start <= 1'b1; host_state <= H_WAIT_POLL;
                end
                H_WAIT_POLL: begin
                    if (txn_done) begin
                        status[7:0] <= txn_read_buf[7:0];
                        if (!txn_read_buf[0]) begin  // WIP clear: operation complete
                            ok <= 1'b1; done <= 1'b1; busy <= 1'b0;
                            host_state <= H_IDLE;
                        end else if (
                            (op_reg == OP_ERASE64 && poll_count >= POLL_LIMIT_ERASE) ||
                            (op_reg != OP_ERASE64 && poll_count >= POLL_LIMIT_PROGRAM)
                        ) begin
                            ok <= 1'b0; done <= 1'b1; busy <= 1'b0;
                            host_state <= H_IDLE;
                        end else begin
                            poll_count <= poll_count + 18'd1;
                            host_state <= H_LAUNCH_POLL;
                        end
                    end
                end
                default: host_state <= H_IDLE;
            endcase
        end
    end
endmodule
