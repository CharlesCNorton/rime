# RIME UART Protocol

Binary protocol between the host (Python) and the IcePi Zero board (SystemVerilog service firmware). All communication is host-initiated; the board never sends unsolicited data.

## Framing

- Baud: 115200, 8N1, no flow control
- Request: 1-byte command + optional payload bytes, sent raw (no framing)
- Response: length-prefixed frame `[type, length_lo, length_hi, payload..., crc8]`
  - `type` is `0x01` (response) or `0x02` (error)
  - `length` is the 16-bit little-endian payload length
  - `payload` is the command echo + data (response) or the error record (error)
  - `crc8` (poly `0x07`, init `0x00`) covers `[type, length_lo, length_hi, payload]`

The host reads exactly `3 + length + 1` bytes per response, so frame boundaries
are deterministic and the CRC-8 is validated on every frame. The payload column
in the tables below is the data the host returns after stripping the frame.

## App Mode Commands

| Byte | Name | Request | Response |
|------|------|---------|----------|
| 0x00 | HELLO | — | `[0x00, mode]` (mode: 1 = app, 2 = service) |
| 0x01 | PING | — | `[0x01, 0xAC]` |
| 0x02 | ENTER_SERVICE | — | `[0x02, 0xAC]` then service handoff |
| 0x03 | UNLOCK *(deprecated)* | `[0x52, 0x49, 0x4D, 0x45]` | `[0x03, 0xAC]` |
| 0x04 | EXIT_SERVICE | — | `[0x04, 0xAC]` then app mode |
| 0x05 | UPTIME | — | `[0x05, sec3, sec2, sec1, sec0]` (32-bit big-endian seconds since boot) |
| 0x06 | IDENTITY | — | `[0x06, 'R', 'I', 'M', 'E', app_mode]` |

HELLO, PING, UPTIME, and IDENTITY work in both app mode and service mode. EXIT_SERVICE returns from service mode to app mode. All other service commands are rejected in app mode with an unknown-command error.

The legacy stateful UNLOCK command (0x03) is retained as a benign no-op for backwards compatibility with hosts that still call it before destructive operations. RIME uses an inline-key prefix on every ERASE64 / PROGRAM16 payload instead (see the Flash section below). New hosts should not call UNLOCK.

## Service Mode Commands — Flash

| Byte | Name | Request | Response |
|------|------|---------|----------|
| 0x70 | PROGRAM16 | `[0x52, 0x49, 0x4D, 0x45, addr_hi, addr_mid, addr_lo, 16 data bytes]` | `[0x70, 0xAC]` |
| 0x71 | STATUS | — | `[0x71, sr1, sr2]` |
| 0x72 | READ16 | `[addr_hi, addr_mid, addr_lo]` | `[0x72, 16 data bytes]` |
| 0x73 | INFO | — | `[0x73, caps0, caps1, max_prog, read_chunk, erase_log2, page_log2, addr_bytes]` |
| 0x74 | JEDEC | — | `[0x74, mfr, dev, cap]` |
| 0x75 | ERASE64 | `[0x52, 0x49, 0x4D, 0x45, addr_hi, addr_mid, addr_lo]` | `[0x75, 0xAC]` |
| 0x76 | LAST_ERROR | — | `[0x76, code, cmd, detail, state_hi, state_lo, valid]` |
| 0x77 | STATS | — | `[0x77, cmd_hi, cmd_lo, erase_hi, erase_lo, prog_hi, prog_lo, err_hi, err_lo]` |
| 0x78 | CLEAR_ERROR | — | `[0x78, 0xAC]` |
| 0x79 | DEBUG | — | `[0x79, reserved, state, cmd, spi_op, addr_idx, data_idx, resp_len, resp_pos, flags, ...]` |

ERASE64 and PROGRAM16 carry an inline 4-byte `RIME` (`0x52 0x49 0x4D 0x45`) prefix as the first four payload bytes. The firmware checks the prefix and rejects the command with an unknown_command error if it does not match. There is no stateful unlock or expiry timer; the key validates per-operation. The legacy `UNLOCK` command (0x03) is retained as a benign no-op for backwards compatibility but is deprecated.

## Service Mode Commands — SD

| Byte | Name | Request | Response |
|------|------|---------|----------|
| 0x7A | SD_INFO | — | `[0x7A, flags, last_err, last_r1, chunk_bytes, chunks_per_block, dbg_state, dbg_shift_in, dbg_shift_busy, svc_state]` |
| 0x7B | SD_INIT | — | `[0x7B, 0xAC]` |
| 0x7C | SD_READ16 | `[lba_3, lba_2, lba_1, lba_0, chunk_idx]` | `[0x7C, 16 data bytes]` |
| 0x7D | SD_INSTALL | `[lba_3, lba_2, lba_1, lba_0]` | `[0x7D, 0xAC]` (long timeout) |
| 0x7E | SD_CRC32 | `[lba_3, lba_2, lba_1, lba_0]` | `[0x7E, crc_3, crc_2, crc_1, crc_0]` |
| 0x7F | SD_WRITE512 | `[lba_3, lba_2, lba_1, lba_0, 512 data bytes]` | `[0x7F, 0xAC]` |
| 0x6F | SD_CRC32_RANGE | `[lba_3, lba_2, lba_1, lba_0, count_hi, count_lo]` | `[0x6F, crc_3, crc_2, crc_1, crc_0]` |

## Service Mode Commands — SDRAM

| Byte | Name | Request | Response |
|------|------|---------|----------|
| 0x80 | SDRAM_INFO | — | `[0x80, flags, caps2]` |
| 0x81 | SDRAM_READ16 | `[word_addr_hi, word_addr_mid, word_addr_lo]` | `[0x81, 16 data bytes]` |
| 0x82 | SDRAM_WRITE16 | `[word_addr_hi, word_addr_mid, word_addr_lo, 16 data bytes]` | `[0x82, 0xAC]` |
| 0x83 | SDRAM_TO_FLASH | `[flash_addr_hi, flash_addr_mid, flash_addr_lo, count_hi, count_mid, count_lo]` | `[0x83, 0xAC]` |
| 0x84 | SDRAM_WRITE_STREAM | `[word_addr_hi, word_addr_mid, word_addr_lo, len_hi, len_lo, data...]` | `[0x84, 0xAC]` |
| 0x85 | SDRAM_VERIFY_FLASH | `[flash_addr_hi, flash_addr_mid, flash_addr_lo, count_hi, count_mid, count_lo]` | `[0x85, 0xAC]` |

## Service Mode Commands — Raw SDRAM

| Byte | Name | Request | Response |
|------|------|---------|----------|
| 0x90 | RAW_WRITE | `[word_addr_hi, word_addr_mid, word_addr_lo, data_hi, data_lo]` | `[0x90, 0xAC]` |
| 0x91 | RAW_READ | `[word_addr_hi, word_addr_mid, word_addr_lo]` | `[0x91, data_hi, data_lo]` |

RAW_WRITE and RAW_READ bypass the 16-byte SDRAM bridge and access individual 16-bit words directly through the SDRAM controller. Useful for probing single addresses without the 8-word burst of SDRAM_READ16/SDRAM_WRITE16.

## Service Mode Commands — System

| Byte | Name | Request | Response |
|------|------|---------|----------|
| 0x86 | SW_RESET | — | `[0x86, 0xAC]` then board resets |
| 0x87 | SET_WATCHDOG | `[cycles_3, cycles_2, cycles_1, cycles_0]` | `[0x87, 0xAC]` |

SET_WATCHDOG configures a hardware watchdog timer. The 32-bit cycle count sets the timeout in sys_clk cycles (25 MHz). Any UART command resets the watchdog counter. Sending cycle count 0 disables the watchdog. If the watchdog expires without UART activity, the board resets.

## SD Bundle Install

`CMD_SD_INSTALL` (0x7D) installs a RIME bundle that has been staged on the SD card. The host transmits a 4-byte LBA pointing at the bundle header. The firmware routes the SD card and flash SPI master through `sd_install_engine.sv`, which:

1. Reads the bundle header from the LBA, validates magic (`ICEPIB1\0`),
2. Computes the image start LBA from the bundle header's `image_offset` field,
3. Erases each 64 KiB sector at the bundle's `target_address` as the install walks the payload,
4. Programs the payload from SD into flash 16 bytes at a time.

The command response is delayed until the install completes. Use a long timeout (>30s for typical bitstreams). On success the response is `[0x7D, 0xAC]`. On failure it returns the standard 8-byte error frame with error code 0x07 (sd_failure), 0x08 (bundle_invalid), or 0x05 (spi_failure) and an engine-specific detail byte.

## Error Response

Any command may return `0xFF` instead of the expected echo:

`[0xFF, error_code, state_hi, state_lo, command, detail, flags, spi_op]`

Error codes: 0x01 unknown_command, 0x02 bad_program_length, 0x03 bad_alignment, 0x04 rx_timeout, 0x05 spi_failure, 0x06 busy, 0x07 sd_failure, 0x08 bundle_invalid, 0x09 verify_failed.
