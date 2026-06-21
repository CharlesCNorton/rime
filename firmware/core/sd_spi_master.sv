// sd_spi_master: SD card SPI-mode driver for SDHC/SDXC.
//
// Handles power-up (500 ms wait, 200 dummy clocks), init sequence
// (CMD0 → CMD8 → CMD55/ACMD41 → CMD58), single-block read (CMD17),
// single-block write (CMD24), and CRC-32 computation over a full
// 512-byte block. SDSC cards (CCS=0) are rejected at init.
//
// Operations (active on start pulse):
//   OP_INIT (1)       — full SD init sequence, sets initialized flag
//   OP_READ16 (2)     — read one 16-byte chunk from a 512-byte block
//   OP_CRC32 (3)      — read full block, compute CRC-32 from init seed
//   OP_WRITE (4)      — write 512 bytes from internal block buffer
//   OP_CRC32_CHAIN (5)— CRC-32 continuing from a previous seed (chained)
//
// The 512-byte block buffer is distributed RAM. For reads, the entire
// block is fetched; the chunk_index selects which 16-byte slice to
// return via read_data. For writes, the host pre-loads the buffer
// via load_byte_addr/data/en before issuing OP_WRITE.
//
// SPI clock: 400 kHz during init (CMD0-CMD8), 12 MHz after init.
// Block addressing: SDHC/SDXC use LBA directly (block-addressed).

module sd_spi_master #(
    parameter integer CLK_HZ = 25000000,
    parameter integer SCK_HZ = 400000
) (
    input  wire         clk,
    input  wire         rst,

    input  wire         start,
    input  wire [2:0]   op,
    input  wire [31:0]  lba,
    input  wire [4:0]   chunk_index,

    output logic [7:0]  write_byte_data,
    input  wire  [8:0]  write_byte_addr,

    input  wire  [8:0]  load_byte_addr,
    input  wire  [7:0]  load_byte_data,
    input  wire         load_byte_en,

    output logic        busy,
    output logic        done,
    output logic        ok,

    output logic        card_present,
    output logic        initialized,
    output logic        high_capacity,
    output logic [7:0]  last_error,
    output logic [7:0]  last_r1,

    output logic [127:0] read_data,
    output logic [31:0]  read_crc32,

    input  wire  [31:0] crc_seed,

    output logic        sd_clk,
    output logic        sd_csn,
    output logic        sd_mosi,
    input  wire         sd_miso,
    input  wire         sd_det,

    output logic [4:0]  dbg_state,
    output logic [7:0]  dbg_shift_in,
    output logic        dbg_shift_busy
);

    localparam [2:0] OP_NONE        = 3'd0;
    localparam [2:0] OP_INIT        = 3'd1;
    localparam [2:0] OP_READ16      = 3'd2;
    localparam [2:0] OP_CRC32       = 3'd3;
    localparam [2:0] OP_WRITE       = 3'd4;
    localparam [2:0] OP_CRC32_CHAIN = 3'd5;

    localparam [7:0] ERR_NONE       = 8'h00;
    localparam [7:0] ERR_NO_MEDIA   = 8'h01;
    localparam [7:0] ERR_TIMEOUT    = 8'h02;
    localparam [7:0] ERR_CMD0       = 8'h03;
    localparam [7:0] ERR_CMD8       = 8'h04;
    localparam [7:0] ERR_ACMD41     = 8'h05;
    localparam [7:0] ERR_CMD58      = 8'h06;
    localparam [7:0] ERR_CMD17      = 8'h08;
    localparam [7:0] ERR_DATA_TOKEN = 8'h09;
    localparam [7:0] ERR_BAD_CHUNK  = 8'h0A;
    localparam [7:0] ERR_CMD24      = 8'h0C;
    localparam [7:0] ERR_DATA_RESP  = 8'h0D;
    localparam [7:0] ERR_WRITE_BUSY = 8'h0E;

    localparam integer INIT_DIV = (CLK_HZ / (SCK_HZ * 2)) < 1 ? 1 : (CLK_HZ / (SCK_HZ * 2));
    localparam integer FAST_DIV = (CLK_HZ / (12000000 * 2)) < 1 ? 1 : (CLK_HZ / (12000000 * 2));
    localparam integer TIMEOUT  = 500000;

    logic [15:0] div_limit;

    logic [7:0]  sh_out, sh_in;
    logic [2:0]  sh_bit;
    logic        sh_busy, sh_done, sh_start;
    logic [7:0]  sh_tx;
    logic        sh_phase;
    logic [15:0] sh_div;

    always_ff @(posedge clk) begin
        sh_done <= 1'b0;
        if (rst) begin
            sh_busy<=0; sh_in<=8'hFF; sd_clk<=0; sd_mosi<=1; sh_phase<=0; sh_div<=0;
        end else if (sh_start && !sh_busy) begin
            sh_busy<=1; sh_out<=sh_tx; sh_in<=0; sh_bit<=7; sh_phase<=0; sh_div<=0;
            sd_clk<=0; sd_mosi<=sh_tx[7];
        end else if (sh_busy) begin
            if (sh_div < div_limit) sh_div <= sh_div+1;
            else begin
                sh_div <= 0;
                if (!sh_phase) begin
                    sd_clk<=1; sh_phase<=1; sh_in[sh_bit]<=sd_miso;
                end else begin
                    sd_clk<=0; sh_phase<=0;
                    if (sh_bit==0) begin sh_busy<=0; sh_done<=1; end
                    else begin sh_bit<=sh_bit-1; sd_mosi<=sh_out[sh_bit-1]; end
                end
            end
        end
    end

    localparam [4:0] S_IDLE       = 0,  S_POWER      = 1,
                     S_SEND_CMD   = 2,  S_WAIT_R1    = 3,
                     S_WAIT_R7    = 4,  S_DISPATCH    = 5,
                     S_INIT55     = 6,  S_INIT41     = 7,
                     S_WAIT_TOKEN = 8,  S_READ_DATA  = 9,
                     S_READ_CRC   = 10, S_READ_DONE  = 11,
                     S_WRITE_TOK  = 12, S_WRITE_DATA = 13,
                     S_WRITE_CRC  = 14, S_WRITE_RESP = 15,
                     S_WRITE_BUSY = 16, S_FAIL       = 17,
                     S_EXTRACT    = 18;

    logic [4:0]  state, after_resp;
    logic [2:0]  op_reg;
    logic [31:0] lba_reg;
    logic [4:0]  chunk_reg;

    logic [7:0]  cmd [0:5];
    logic [2:0]  cmd_idx;
    logic [4:0]  extra_resp;
    logic [4:0]  extra_idx;
    logic [39:0] resp_buf;

    logic [9:0]  didx;
    logic [23:0] tmo;
    logic [15:0] acmd41_cnt;

    // 512-byte block buffer: holds one complete SD sector.
    // For reads, the entire block is fetched from the card; chunk_index
    // selects which 16-byte slice to expose on read_data.
    // For writes, the host pre-loads bytes via load_byte_addr/data/en.
    (* ram_style = "distributed" *) reg [7:0] blk [0:511];
    logic [31:0] crc_acc;   // running CRC-32 for block-level integrity
    logic        crc_run;   // CRC bit-stepper active
    logic [2:0]  crc_stp;   // bit index within one CRC byte (0-7)

    logic [15:0] init_cnt, read_cnt;  // diagnostic counters

    // SDHC/SDXC only: block-addressed CMD17/24. SDSC is not supported.
    wire [31:0] sd_cmd_addr = lba;

    assign card_present = 1'b1;
    assign dbg_state = state;
    assign dbg_shift_in = sh_in;
    assign dbg_shift_busy = sh_busy;

    logic [8:0]  blk_rd_addr;
    logic [7:0]  blk_rd_data;
    logic [8:0]  blk_wr_addr;
    logic [7:0]  blk_wr_data;
    logic        blk_wr_en;
    always_comb begin
        blk_rd_data = blk[blk_rd_addr];
    end
    always_ff @(posedge clk) begin
        if (blk_wr_en)
            blk[blk_wr_addr] <= blk_wr_data;
    end
    // Block buffer read-address mux: three consumers share the read port.
    // EXTRACT/READ_DONE: reading a 16-byte chunk for the host.
    // WRITE_DATA/WRITE_TOK: streaming buffer contents to the SD card.
    // Default: exposes the buffer to the service's sd_write_addr for readback.
    always_comb begin
        if (state == S_EXTRACT || state == S_READ_DONE)
            blk_rd_addr = {chunk_reg, 4'd0} + {4'd0, extract_idx};
        else if (state == S_WRITE_DATA || state == S_WRITE_TOK)
            blk_rd_addr = didx[8:0];
        else
            blk_rd_addr = write_byte_addr;
    end
    assign write_byte_data = blk_rd_data;

    wire reading_sd = (state == S_READ_DATA) && sh_done;
    always_comb begin
        if (reading_sd) begin
            blk_wr_en   = 1'b1;
            blk_wr_addr = didx[8:0];
            blk_wr_data = sh_in;
        end else if (load_byte_en) begin
            blk_wr_en   = 1'b1;
            blk_wr_addr = load_byte_addr;
            blk_wr_data = load_byte_data;
        end else begin
            blk_wr_en   = 1'b0;
            blk_wr_addr = 9'd0;
            blk_wr_data = 8'd0;
        end
    end

    logic [3:0]  extract_idx;

    always_ff @(posedge clk) begin
        sh_start <= 0;

        if (crc_run) begin
            crc_acc <= crc_acc[0] ? (crc_acc>>1) ^ 32'hEDB88320 : (crc_acc>>1);
            if (crc_stp==7) crc_run<=0; else crc_stp<=crc_stp+1;
        end

        if (rst) begin
            state<=S_IDLE; busy<=0; ok<=0; done<=0; sd_csn<=1;
            initialized<=0; high_capacity<=0;
            last_error<=ERR_NONE; last_r1<=8'hFF;
            read_data<=0; read_crc32<=0;
            div_limit<=INIT_DIV[15:0];
            init_cnt<=0; read_cnt<=0; crc_run<=0;
        end else case (state)

        S_IDLE: begin
            busy<=0; sd_csn<=1;
            if (start) begin
                busy<=1; ok<=0; done<=0; op_reg<=op; lba_reg<=lba; chunk_reg<=chunk_index;
                case (op)
                    OP_INIT: begin
                        div_limit<=INIT_DIV[15:0]; didx<=0; tmo<=0; state<=S_POWER;
                    end
                    OP_READ16, OP_CRC32, OP_CRC32_CHAIN: begin
                        div_limit<=FAST_DIV[15:0]; read_cnt<=read_cnt+1;
                        sd_csn<=0;
                        cmd[0]<=8'h40|8'd17;
                        cmd[1]<=sd_cmd_addr[31:24]; cmd[2]<=sd_cmd_addr[23:16];
                        cmd[3]<=sd_cmd_addr[15:8];  cmd[4]<=sd_cmd_addr[7:0];
                        cmd[5]<=8'hFF;
                        cmd_idx<=0; extra_resp<=0; after_resp<=S_WAIT_TOKEN;
                        state<=S_SEND_CMD;
                    end
                    OP_WRITE: begin
                        div_limit<=FAST_DIV[15:0]; sd_csn<=0;
                        cmd[0]<=8'h40|8'd24;
                        cmd[1]<=sd_cmd_addr[31:24]; cmd[2]<=sd_cmd_addr[23:16];
                        cmd[3]<=sd_cmd_addr[15:8];  cmd[4]<=sd_cmd_addr[7:0];
                        cmd[5]<=8'hFF;
                        cmd_idx<=0; extra_resp<=0; after_resp<=S_WRITE_TOK;
                        didx<=0;
                        state<=S_SEND_CMD;
                    end
                    default: begin busy<=0; done<=1; end
                endcase
            end
        end

        S_POWER: begin
            if (!card_present) begin
                last_error<=ERR_NO_MEDIA; state<=S_FAIL;
            end else if (tmo < 24'd12500000) begin
                sd_csn<=1; tmo<=tmo+24'd1;
            end else if (!sh_busy && !sh_start) begin
                if (didx < 200) begin
                    sd_csn<=1;
                    sh_start<=1; sh_tx<=8'hFF; didx<=didx+1;
                end else if (didx < 204) begin
                    sd_csn<=0;
                    sh_start<=1; sh_tx<=8'hFF; didx<=didx+1;
                end else begin
                    sd_csn<=0; acmd41_cnt<=0;
                    cmd[0]<=8'h40; cmd[1]<=0; cmd[2]<=0; cmd[3]<=0; cmd[4]<=0; cmd[5]<=8'h95;
                    cmd_idx<=0; extra_resp<=0; after_resp<=S_DISPATCH;
                    state<=S_SEND_CMD;
                end
            end
        end

        S_SEND_CMD: begin
            if (!sh_busy && !sh_start) begin
                if (cmd_idx < 6) begin
                    sh_start<=1; sh_tx<=cmd[cmd_idx]; cmd_idx<=cmd_idx+1;
                end else begin
                    tmo<=0; extra_idx<=0; state<=S_WAIT_R1;
                end
            end
        end

        S_WAIT_R1: begin
            if (!sh_busy && !sh_start) begin
                if (tmo > TIMEOUT[23:0]) begin
                    last_error<=ERR_TIMEOUT; state<=S_FAIL;
                end else begin
                    sh_start<=1; sh_tx<=8'hFF; tmo<=tmo+1;
                end
            end
            if (sh_done && sh_in != 8'hFF) begin
                last_r1 <= sh_in;
                resp_buf[39:32] <= sh_in;
                if (extra_resp > 0) begin
                    extra_idx<=0; state<=S_WAIT_R7;
                end else begin
                    state <= after_resp;
                end
            end
        end

        S_WAIT_R7: begin
            if (!sh_busy && !sh_start) begin
                sh_start<=1; sh_tx<=8'hFF;
            end
            if (sh_done) begin
                resp_buf[31 - (extra_idx*8) -: 8] <= sh_in;
                if (extra_idx + 1 >= extra_resp) state <= after_resp;
                else extra_idx <= extra_idx + 1;
            end
        end

        // SD init dispatch: reuses S_DISPATCH as a continuation state.
        // Each command response returns here; cmd[0][5:0] identifies which
        // command just completed. The init sequence is:
        //   CMD0 (go idle) → CMD8 (voltage check) → CMD55+ACMD41 (init loop)
        //   → CMD58 (read OCR, check CCS bit for SDHC)
        S_DISPATCH: begin
            case (cmd[0][5:0])
                6'd0: begin  // CMD0 response: card should be in idle (R1=0x01)
                    if (last_r1 != 8'h01) begin last_error<=ERR_CMD0; state<=S_FAIL; end
                    else begin
                        // CMD8: voltage range check (0x1AA pattern, CRC=0x87)
                        cmd[0]<=8'h48; cmd[1]<=0; cmd[2]<=0; cmd[3]<=8'h01; cmd[4]<=8'hAA; cmd[5]<=8'h87;
                        cmd_idx<=0; extra_resp<=4; after_resp<=S_DISPATCH;
                        state<=S_SEND_CMD;
                    end
                end
                6'd8: begin  // CMD8 response: confirms SD v2+ protocol
                    if (last_r1 != 8'h01) begin last_error<=ERR_CMD8; state<=S_FAIL; end
                    else state <= S_INIT55;
                end
                6'd55: begin  // CMD55 response: app-command prefix acknowledged
                    // ACMD41: send HCS=1 to indicate host supports SDHC
                    cmd[0]<=8'h40|8'd41; cmd[1]<=8'h40; cmd[2]<=8'hFF; cmd[3]<=8'h80; cmd[4]<=8'h00; cmd[5]<=8'hFF;
                    cmd_idx<=0; extra_resp<=0; after_resp<=S_DISPATCH;
                    state<=S_SEND_CMD;
                end
                6'd41: begin  // ACMD41 response: R1=0x00 means init complete
                    if (last_r1 == 8'h00) begin
                        // Init done — read OCR via CMD58 to check CCS bit
                        cmd[0]<=8'h40|8'd58; cmd[1]<=0; cmd[2]<=0; cmd[3]<=0; cmd[4]<=0; cmd[5]<=8'hFF;
                        cmd_idx<=0; extra_resp<=4; after_resp<=S_DISPATCH;
                        state<=S_SEND_CMD;
                    end else if (acmd41_cnt > 50000) begin
                        last_error<=ERR_ACMD41; state<=S_FAIL;
                    end else begin
                        acmd41_cnt<=acmd41_cnt+1; state<=S_INIT55;
                    end
                end
                6'd58: begin  // CMD58 response: OCR register, bit 30 = CCS
                    if (last_r1 != 8'h00) begin last_error<=ERR_CMD58; state<=S_FAIL; end
                    else if (!resp_buf[30]) begin
                        // SDSC cards (CCS=0) are not supported. Fail the init.
                        last_error<=ERR_CMD58; state<=S_FAIL;
                    end else begin
                        high_capacity <= 1'b1;
                        initialized <= 1;
                        init_cnt <= init_cnt + 1;
                        last_error <= ERR_NONE;
                        div_limit <= FAST_DIV[15:0];
                        ok<=1; sd_csn<=1; done<=1; state<=S_IDLE;
                    end
                end
                default: state<=S_FAIL;
            endcase
        end

        S_INIT55: begin
            cmd[0]<=8'h40|8'd55; cmd[1]<=0; cmd[2]<=0; cmd[3]<=0; cmd[4]<=0; cmd[5]<=8'hFF;
            cmd_idx<=0; extra_resp<=0; after_resp<=S_DISPATCH;
            state<=S_SEND_CMD;
        end

        S_WAIT_TOKEN: begin
            if (last_r1[7:1] != 0) begin
                last_error <= (op_reg==OP_WRITE) ? ERR_CMD24 : ERR_CMD17;
                state <= S_FAIL;
            end else if (!sh_busy && !sh_start) begin
                if (tmo > TIMEOUT[23:0]) begin last_error<=ERR_DATA_TOKEN; state<=S_FAIL; end
                else begin sh_start<=1; sh_tx<=8'hFF; tmo<=tmo+1; end
            end
            if (sh_done && sh_in==8'hFE) begin
                didx<=0;
                crc_acc <= (op_reg == OP_CRC32_CHAIN) ? ~crc_seed : 32'hFFFFFFFF;
                state<=S_READ_DATA;
            end
        end

        // Read 512 bytes into the block buffer, computing CRC-32 as each
        // byte arrives. The block buffer write happens combinationally via
        // the reading_sd signal above.
        S_READ_DATA: begin
            if (!sh_busy && !sh_start) begin sh_start<=1; sh_tx<=8'hFF; end
            if (sh_done) begin
                // XOR byte into CRC accumulator, then kick the 8-cycle bit stepper
                crc_acc <= crc_acc ^ {24'd0, sh_in};
                crc_run<=1; crc_stp<=0;
                if (didx==511) begin didx<=0; state<=S_READ_CRC; end
                else didx<=didx+1;
            end
        end

        S_READ_CRC: begin
            // Consume the 2-byte SD CRC trailer (discarded; we compute our own)
            if (!sh_busy && !sh_start && !crc_run) begin sh_start<=1; sh_tx<=8'hFF; end
            if (sh_done) begin
                if (didx==0) didx<=1;
                else state<=S_READ_DONE;
            end
        end

        S_READ_DONE: begin
            read_crc32 <= ~crc_acc;  // final complement
            if (op_reg == OP_READ16) begin
                if (chunk_reg > 31) begin
                    last_error<=ERR_BAD_CHUNK; ok<=0;
                    sd_csn<=1; done<=1; state<=S_IDLE;
                end else begin
                    extract_idx <= 4'd0;
                    state <= S_EXTRACT;
                end
            end else begin
                ok<=1; sd_csn<=1; done<=1; state<=S_IDLE;
            end
        end

        S_EXTRACT: begin
            // Copy 16 bytes from the block buffer at the requested chunk offset
            // into the read_data output register, one byte per cycle.
            read_data[127 - (extract_idx * 8) -: 8] <= blk_rd_data;
            if (extract_idx == 4'd15) begin
                ok<=1; sd_csn<=1; done<=1; state<=S_IDLE;
            end else begin
                extract_idx <= extract_idx + 4'd1;
            end
        end

        S_WRITE_TOK: begin
            if (last_r1[7:1] != 0) begin last_error<=ERR_CMD24; state<=S_FAIL; end
            else if (!sh_busy && !sh_start) begin
                sh_start<=1; sh_tx<=8'hFE; didx<=10'd0; state<=S_WRITE_DATA;
            end
        end

        S_WRITE_DATA: begin
            if (sh_done) begin
                if (didx==512) begin didx<=0; state<=S_WRITE_CRC; end
                else begin sh_start<=1; sh_tx<=blk_rd_data; didx<=didx+1; end
            end
        end

        S_WRITE_CRC: begin
            if (!sh_busy && !sh_start) begin
                if (didx==0) begin sh_start<=1; sh_tx<=8'hFF; didx<=1; end
                else begin sh_start<=1; sh_tx<=8'hFF; state<=S_WRITE_RESP; end
            end
        end

        S_WRITE_RESP: begin
            if (sh_done) begin
                if (sh_in == 8'hFF) begin
                    if (tmo > TIMEOUT[23:0]) begin last_error<=ERR_DATA_RESP; state<=S_FAIL; end
                    else begin sh_start<=1; sh_tx<=8'hFF; tmo<=tmo+1; end
                end else if ((sh_in & 8'h1F)==8'h05) begin tmo<=0; state<=S_WRITE_BUSY; end
                else begin last_error<=ERR_DATA_RESP; state<=S_FAIL; end
            end else if (!sh_busy && !sh_start) begin
                sh_start<=1; sh_tx<=8'hFF;
            end
        end

        S_WRITE_BUSY: begin
            if (!sh_busy && !sh_start) begin
                if (tmo > TIMEOUT[23:0]) begin last_error<=ERR_WRITE_BUSY; state<=S_FAIL; end
                else begin sh_start<=1; sh_tx<=8'hFF; tmo<=tmo+1; end
            end
            if (sh_done && sh_in==8'hFF) begin
                ok<=1; sd_csn<=1; done<=1; state<=S_IDLE;
            end
        end

        S_FAIL: begin
            ok<=0; sd_csn<=1; done<=1; state<=S_IDLE;
        end

        default: begin last_error<=ERR_TIMEOUT; ok<=0; done<=1; state<=S_IDLE; end
        endcase
    end
endmodule
