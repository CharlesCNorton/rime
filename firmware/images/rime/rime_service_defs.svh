// rime_service_defs.svh — Command IDs, capabilities, FSM states, error codes.
// Extracted from rime_service.sv to reduce monolithic file size.
// This file is `included inside the rime_service module scope.

// ---- COMMAND_IDS ----
localparam [7:0] CMD_HELLO      = 8'h00;
localparam [7:0] CMD_PING         = 8'h01;
localparam [7:0] CMD_ENTER_SERVICE = 8'h02;
localparam [7:0] CMD_UNLOCK      = 8'h03;
localparam [7:0] CMD_EXIT_SERVICE = 8'h04;
localparam [7:0] CMD_UPTIME      = 8'h05;
localparam [7:0] CMD_IDENTITY    = 8'h06;
localparam [7:0] CMD_PROGRAM16    = 8'h70;
localparam [7:0] CMD_STATUS       = 8'h71;
localparam [7:0] CMD_READ16       = 8'h72;
localparam [7:0] CMD_INFO         = 8'h73;
localparam [7:0] CMD_JEDEC        = 8'h74;
localparam [7:0] CMD_ERASE64      = 8'h75;
localparam [7:0] CMD_LAST_ERROR   = 8'h76;
localparam [7:0] CMD_STATS        = 8'h77;
localparam [7:0] CMD_CLEAR_ERROR  = 8'h78;
localparam [7:0] CMD_DEBUG        = 8'h79;
localparam [7:0] CMD_SDRAM_INFO   = 8'h80;
localparam [7:0] CMD_SDRAM_READ16 = 8'h81;
localparam [7:0] CMD_SDRAM_WRITE16 = 8'h82;
localparam [7:0] CMD_SDRAM_TO_FLASH = 8'h83;
localparam [7:0] CMD_SDRAM_WRITE_STREAM = 8'h84;
localparam [7:0] CMD_SDRAM_VERIFY_FLASH = 8'h85;
localparam [7:0] CMD_SD_INFO   = 8'h7A;
localparam [7:0] CMD_SD_INIT   = 8'h7B;
localparam [7:0] CMD_SD_READ16 = 8'h7C;
localparam [7:0] CMD_SD_INSTALL = 8'h7D;
localparam [7:0] CMD_SD_CRC32  = 8'h7E;
localparam [7:0] CMD_SD_CRC32_RANGE = 8'h6F;
localparam [7:0] CMD_SD_WRITE512 = 8'h7F;
localparam [7:0] CMD_SW_RESET  = 8'h86;
localparam [7:0] CMD_SET_WATCHDOG = 8'h87;
localparam [7:0] CMD_RAW_WRITE = 8'h90;
localparam [7:0] CMD_RAW_READ  = 8'h91;

// ---- MODE + CAPS ----
localparam [7:0] MODE_APP     = 8'd1;
localparam [7:0] MODE_SERVICE = 8'd2;
localparam [7:0] ACK   = 8'hAC;
localparam [7:0] CAPS0 = 8'b11111111;
localparam [7:0] CAPS1 = 8'b11111111;
localparam [7:0] CAPS2 = 8'b00000111;

// ---- FSM_STATES ----
localparam [4:0] S_IDLE       = 5'd0;
localparam [4:0] S_DISPATCH   = 5'd1;
localparam [4:0] S_TX_RESP    = 5'd2;
localparam [4:0] S_RX_BYTES   = 5'd3;
localparam [4:0] S_WAIT_SPI   = 5'd4;
localparam [4:0] S_WAIT_SDRAM = 5'd5;
localparam [4:0] S_SDRAM_FLASH_LOOP = 5'd6;
localparam [4:0] S_SDRAM_STREAM     = 5'd7;
localparam [4:0] S_SDRAM_VERIFY     = 5'd8;
localparam [4:0] S_RAW_WAIT_ACK    = 5'd9;
localparam [4:0] S_RAW_WAIT_DONE   = 5'd10;
localparam [4:0] S_RAW_READ_DONE   = 5'd11;
localparam [4:0] S_WAIT_SD         = 5'd12;
localparam [4:0] S_SD_WRITE_RX    = 5'd13;
localparam [4:0] S_RAW_READ_LOOP   = 5'd14;
localparam [4:0] S_RAW_READ_CAP    = 5'd15;
localparam [4:0] S_WAIT_INSTALL    = 5'd16;
