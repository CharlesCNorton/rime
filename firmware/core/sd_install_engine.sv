// sd_install_engine: firmware-mediated SD bundle installer.
//
// Reads a RIME bundle from SD, validates the header (magic,
// block size, image length), then erases flash sectors and programs
// the payload in 16-byte chunks. Operates autonomously once started —
// the host (or auto_recovery) pulses start with the bundle LBA and
// waits for done.
//
// Bundle format on SD (see icepi/models.py for the Python definition):
//   LBA+0: 512-byte header — magic "ICEPIB1\0", offsets, target addr
//   LBA+N: payload blocks — raw bitstream data, 16-byte aligned
//
// The engine reads 3 header chunks (48 bytes) to extract geometry,
// then walks the payload: for each 16-byte chunk, it reads from SD
// and programs to flash at the target address. Erase is triggered
// at each 64 KiB sector boundary.
//
// Error codes (output on error_code):
//   0x07 — SD read failure (detail from sd_ok)
//   0x08 — invalid bundle header (detail: 0x01=magic,
//           0x03=block_size, 0x05=image_length)
//   0x05 — SPI flash failure (detail: 0x04=erase, 0x05=program)
//
// Shares the SD and SPI flash masters via top.sv bus mux. While
// busy, inst_active routes both masters to this engine.

module sd_install_engine (
    input  wire        clk,
    input  wire        rst,

    input  wire        start,
    input  wire [31:0] bundle_lba,
    output logic       busy,
    output logic       done,
    output logic       ok,
    output logic [7:0] error_code,
    output logic [7:0] error_detail,

    output logic [2:0]  spi_op,
    output logic [23:0] spi_addr,
    output logic [127:0] spi_prog_data,
    output logic        spi_start,
    input  wire         spi_done,
    input  wire         spi_ok,

    output logic        sd_start,
    output logic [2:0]  sd_op,
    output logic [31:0] sd_lba,
    output logic [4:0]  sd_chunk_idx,
    input  wire         sd_done,
    input  wire         sd_ok,
    input  wire [127:0] sd_read_data
);

    localparam [3:0] S_IDLE       = 4'd0;
    localparam [3:0] S_HDR_READ   = 4'd1;
    localparam [3:0] S_HDR_WAIT   = 4'd2;
    localparam [3:0] S_VALIDATE   = 4'd3;
    localparam [3:0] S_ERASE      = 4'd4;
    localparam [3:0] S_ERASE_WAIT = 4'd5;
    localparam [3:0] S_SD_READ    = 4'd6;
    localparam [3:0] S_SD_WAIT    = 4'd7;
    localparam [3:0] S_PROGRAM    = 4'd8;
    localparam [3:0] S_PROG_WAIT  = 4'd9;
    localparam [3:0] S_ADVANCE    = 4'd10;
    localparam [3:0] S_DONE       = 4'd11;
    localparam [3:0] S_ERROR      = 4'd12;
    localparam [3:0] S_INIT_WAIT  = 4'd13;

    localparam [63:0] BUNDLE_MAGIC = 64'h4943455049423100;

    logic [3:0] state;

    logic [127:0] hdr0, hdr1, hdr2;
    logic [1:0]   hdr_idx;

    logic spi_done_l, spi_ok_l, sd_done_l, sd_ok_l;

    function automatic [31:0] le32(input [127:0] chunk, input integer byte_off);
        le32 = {chunk[(15-byte_off-3)*8 +: 8],
                chunk[(15-byte_off-2)*8 +: 8],
                chunk[(15-byte_off-1)*8 +: 8],
                chunk[(15-byte_off  )*8 +: 8]};
    endfunction

    // Decode bundle header fields from the three 16-byte SD chunks.
    // Bundle header is 512 bytes; only the first 48 bytes are parsed.
    wire [63:0]  hdr_magic      = hdr0[127:64];       // "ICEPIB1\0"
    wire [31:0]  hdr_block_size = le32(hdr0, 12);
    wire [31:0]  hdr_img_offset = le32(hdr1, 4);
    wire [31:0]  hdr_img_bytes  = le32(hdr1, 8);
    wire [31:0]  hdr_target     = le32(hdr2, 0);

    logic [31:0] img_start_lba;
    logic [23:0] flash_addr;
    logic [23:0] remaining;
    logic [31:0] cur_sd_lba;
    logic [4:0]  cur_sd_chunk;

    always_ff @(posedge clk) begin
        spi_start <= 1'b0;
        sd_start  <= 1'b0;
        done      <= 1'b0;

        // Done-latches with start-clears-first priority (same pattern as auto_recovery)
        if (spi_start)     begin spi_done_l <= 1'b0; spi_ok_l <= 1'b0; end
        else if (spi_done) begin spi_done_l <= 1'b1; spi_ok_l <= spi_ok; end
        if (sd_start)      begin sd_done_l <= 1'b0; sd_ok_l <= 1'b0; end
        else if (sd_done)  begin sd_done_l <= 1'b1; sd_ok_l <= sd_ok; end

        if (rst) begin
            state <= S_IDLE;
            busy  <= 1'b0;
            ok    <= 1'b0;
            spi_done_l <= 1'b0;
            spi_ok_l   <= 1'b0;
            sd_done_l  <= 1'b0;
            sd_ok_l    <= 1'b0;
            error_code   <= 8'd0;
            error_detail <= 8'd0;
        end else case (state)

            S_IDLE: begin
                busy <= 1'b0;
                if (start) begin
                    busy       <= 1'b1;
                    hdr_idx    <= 2'd0;
                    sd_done_l  <= 1'b0;
                    spi_done_l <= 1'b0;
                    state      <= S_HDR_READ;
                end
            end

            S_HDR_READ: begin
                sd_op        <= 3'd2;
                sd_lba       <= bundle_lba;
                sd_chunk_idx <= {3'd0, hdr_idx};
                sd_start     <= 1'b1;
                sd_done_l    <= 1'b0;
                state        <= S_HDR_WAIT;
            end

            S_HDR_WAIT: begin
                if (sd_done_l) begin
                    if (!sd_ok_l) begin
                        error_code   <= 8'h07;
                        error_detail <= 8'h09;
                        state        <= S_ERROR;
                    end else begin
                        case (hdr_idx)
                            2'd0: hdr0 <= sd_read_data;
                            2'd1: hdr1 <= sd_read_data;
                            2'd2: hdr2 <= sd_read_data;
                            default: ;
                        endcase
                        if (hdr_idx == 2'd2)
                            state <= S_VALIDATE;
                        else begin
                            hdr_idx <= hdr_idx + 2'd1;
                            state   <= S_HDR_READ;
                        end
                    end
                end
            end

            S_VALIDATE: begin
                if (hdr_magic != BUNDLE_MAGIC) begin
                    error_code <= 8'h08; error_detail <= 8'h01;
                    state <= S_ERROR;
                end else if (hdr_block_size == 32'd0) begin
                    error_code <= 8'h08; error_detail <= 8'h03;
                    state <= S_ERROR;
                end else if (hdr_img_bytes == 32'd0) begin
                    error_code <= 8'h08; error_detail <= 8'h05;
                    state <= S_ERROR;
                end else begin
                    img_start_lba <= bundle_lba + (hdr_img_offset >> 9);
                    flash_addr    <= hdr_target[23:0];
                    remaining     <= hdr_img_bytes[23:0];
                    cur_sd_lba    <= bundle_lba + (hdr_img_offset >> 9);
                    cur_sd_chunk  <= 5'd0;
                    state         <= S_ERASE;
                end
            end

            S_ERASE: begin
                if (remaining == 24'd0 || remaining[23]) begin
                    ok    <= 1'b1;
                    state <= S_DONE;
                end else if (flash_addr[15:0] == 16'd0) begin
                    spi_op       <= 3'd4;
                    spi_addr     <= flash_addr;
                    spi_start    <= 1'b1;
                    spi_done_l   <= 1'b0;
                    state        <= S_ERASE_WAIT;
                end else begin
                    state <= S_SD_READ;
                end
            end

            S_ERASE_WAIT: begin
                if (spi_done_l) begin
                    if (!spi_ok_l) begin
                        error_code <= 8'h05; error_detail <= 8'h04;
                        state <= S_ERROR;
                    end else
                        state <= S_SD_READ;
                end
            end

            S_SD_READ: begin
                sd_op        <= 3'd2;
                sd_lba       <= cur_sd_lba;
                sd_chunk_idx <= cur_sd_chunk;
                sd_start     <= 1'b1;
                sd_done_l    <= 1'b0;
                state        <= S_SD_WAIT;
            end

            S_SD_WAIT: begin
                if (sd_done_l) begin
                    if (!sd_ok_l) begin
                        error_code <= 8'h07; error_detail <= 8'h08;
                        state <= S_ERROR;
                    end else begin
                        spi_op        <= 3'd5;
                        spi_addr      <= flash_addr;
                        spi_prog_data <= sd_read_data;
                        spi_start     <= 1'b1;
                        spi_done_l    <= 1'b0;
                        state         <= S_PROG_WAIT;
                    end
                end
            end

            S_PROGRAM: state <= S_SD_READ;

            S_PROG_WAIT: begin
                if (spi_done_l) begin
                    if (!spi_ok_l) begin
                        error_code <= 8'h05; error_detail <= 8'h05;
                        state <= S_ERROR;
                    end else
                        state <= S_ADVANCE;
                end
            end

            S_ADVANCE: begin
                // Move to next 16-byte chunk. Each SD block has 32 chunks
                // (512 / 16 = 32). When we exhaust a block, advance the LBA.
                flash_addr <= flash_addr + 24'd16;
                remaining  <= remaining - 24'd16;
                if (cur_sd_chunk == 5'd31) begin
                    cur_sd_chunk <= 5'd0;
                    cur_sd_lba   <= cur_sd_lba + 32'd1;
                end else
                    cur_sd_chunk <= cur_sd_chunk + 5'd1;
                // Loop back to S_ERASE which checks sector boundaries
                state <= S_ERASE;
            end

            S_DONE: begin
                done <= 1'b1;
                busy <= 1'b0;
                state <= S_IDLE;
            end

            S_ERROR: begin
                ok   <= 1'b0;
                done <= 1'b1;
                busy <= 1'b0;
                state <= S_IDLE;
            end

            default: state <= S_IDLE;
        endcase
    end
endmodule
