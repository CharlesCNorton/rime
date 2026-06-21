"""RIME UART protocol constants, CRC-8, and human-readable name tables.

This module is the single source of truth for command bytes, error codes,
capability flags, debug flags, and the name-lookup functions used by both
the transport layer (flash_service.py) and the CLI/shell.

All symbols are re-exported by flash_service.py for backwards
compatibility — existing ``from icepi.flash_service import CMD_HELLO``
imports continue to work unchanged.
"""

from __future__ import annotations

__all__ = [
    "crc8",
    "CMD_HELLO", "CMD_PING", "CMD_ENTER_SERVICE", "CMD_UNLOCK",
    "CMD_EXIT_SERVICE", "CMD_UPTIME", "CMD_IDENTITY",
    "CMD_SD_CRC32_RANGE",
    "CMD_PROGRAM16", "CMD_STATUS", "CMD_READ16", "CMD_INFO",
    "CMD_JEDEC", "CMD_ERASE64", "CMD_LAST_ERROR", "CMD_STATS",
    "CMD_CLEAR_ERROR", "CMD_DEBUG",
    "CMD_SD_INFO", "CMD_SD_INIT", "CMD_SD_READ16", "CMD_SD_INSTALL",
    "CMD_SD_CRC32", "CMD_SD_WRITE512",
    "CMD_SDRAM_INFO", "CMD_SDRAM_READ16", "CMD_SDRAM_WRITE16",
    "CMD_SDRAM_TO_FLASH", "CMD_SDRAM_WRITE_STREAM",
    "CMD_SDRAM_VERIFY_FLASH",
    "CMD_SW_RESET", "CMD_SET_WATCHDOG",
    "CMD_RAW_WRITE", "CMD_RAW_READ",
    "RESP_ERROR", "PING_REPLY",
    "MODE_APP", "MODE_SERVICE", "MODE_APP_STARTUP", "MODE_APP_FAILSAFE",
    "ERR_UNKNOWN_CMD", "ERR_BAD_PROG_LEN", "ERR_BAD_ALIGN",
    "ERR_RX_TIMEOUT", "ERR_SPI", "ERR_BUSY", "ERR_SD",
    "ERR_BUNDLE", "ERR_VERIFY",
    "CAPS0_READ16", "CAPS0_ERASE64", "CAPS0_PROGRAM16",
    "CAPS0_STATUS", "CAPS0_INFO", "CAPS0_LAST_ERROR",
    "CAPS0_STATS", "CAPS0_FRAME_CRC",
    "CAPS1_VERIFY_READBACK", "CAPS1_CLEAR_ERROR", "CAPS1_DEBUG",
    "CAPS1_SD_INFO", "CAPS1_SD_INIT", "CAPS1_SD_READ16",
    "CAPS1_SD_INSTALL", "CAPS1_SD_WRITE512",
    "DEBUG_FLAG_RX_ACTIVE", "DEBUG_FLAG_SPI_BUSY",
    "DEBUG_FLAG_RESP_PENDING", "DEBUG_FLAG_LAST_ERROR",
    "DEBUG_FLAG_SD_BUSY", "DEBUG_FLAG_AUTO_ACTIVE",
    "DEBUG_FLAG_AUTO_FALLBACK", "DEBUG_FLAG_SD_PRESENT",
    "command_name", "error_name", "service_state_name",
    "spi_op_name", "sd_error_name", "bundle_error_name",
    "verify_error_name", "auto_state_name", "auto_exit_reason_name",
    "auto_result_name", "auto_progress_text", "debug_flag_names",
    "describe_state_code",
]


# ---------------------------------------------------------------------------
# CRC-8 (polynomial 0x07, init 0x00)
# ---------------------------------------------------------------------------

_CRC8_TABLE = [0] * 256
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = ((_c << 1) ^ 0x07) & 0xFF if _c & 0x80 else (_c << 1) & 0xFF
    _CRC8_TABLE[_i] = _c


def crc8(data: bytes | bytearray) -> int:
    """Compute CRC-8 (polynomial 0x07) over *data*."""
    crc = 0
    for byte in data:
        crc = _CRC8_TABLE[crc ^ byte]
    return crc


# ---------------------------------------------------------------------------
# Command bytes
# ---------------------------------------------------------------------------

CMD_HELLO = 0x00
CMD_PING = 0x01
CMD_ENTER_SERVICE = 0x02
CMD_UNLOCK = 0x03
CMD_EXIT_SERVICE = 0x04
CMD_UPTIME = 0x05
CMD_IDENTITY = 0x06

CMD_SD_CRC32_RANGE = 0x6F
CMD_PROGRAM16 = 0x70
CMD_STATUS = 0x71
CMD_READ16 = 0x72
CMD_INFO = 0x73
CMD_JEDEC = 0x74
CMD_ERASE64 = 0x75
CMD_LAST_ERROR = 0x76
CMD_STATS = 0x77
CMD_CLEAR_ERROR = 0x78
CMD_DEBUG = 0x79
CMD_SD_INFO = 0x7A
CMD_SD_INIT = 0x7B
CMD_SD_READ16 = 0x7C
CMD_SD_INSTALL = 0x7D
CMD_SD_CRC32 = 0x7E
CMD_SD_WRITE512 = 0x7F
CMD_SDRAM_INFO = 0x80
CMD_SDRAM_READ16 = 0x81
CMD_SDRAM_WRITE16 = 0x82
CMD_SDRAM_TO_FLASH = 0x83
CMD_SDRAM_WRITE_STREAM = 0x84
CMD_SDRAM_VERIFY_FLASH = 0x85
CMD_SW_RESET = 0x86
CMD_SET_WATCHDOG = 0x87
CMD_RAW_WRITE = 0x90
CMD_RAW_READ = 0x91


# ---------------------------------------------------------------------------
# Response / handshake constants
# ---------------------------------------------------------------------------

RESP_ERROR = 0xFF
PING_REPLY = 0xAC

# Board mode reported by the handshake (CMD_HELLO).
MODE_APP = 1
MODE_SERVICE = 2
MODE_APP_STARTUP = 3
MODE_APP_FAILSAFE = 4


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

ERR_UNKNOWN_CMD = 0x01
ERR_BAD_PROG_LEN = 0x02
ERR_BAD_ALIGN = 0x03
ERR_RX_TIMEOUT = 0x04
ERR_SPI = 0x05
ERR_BUSY = 0x06
ERR_SD = 0x07
ERR_BUNDLE = 0x08
ERR_VERIFY = 0x09


# ---------------------------------------------------------------------------
# Capability flags (INFO response)
# ---------------------------------------------------------------------------

CAPS0_READ16 = 1 << 0
CAPS0_ERASE64 = 1 << 1
CAPS0_PROGRAM16 = 1 << 2
CAPS0_STATUS = 1 << 3
CAPS0_INFO = 1 << 4
CAPS0_LAST_ERROR = 1 << 5
CAPS0_STATS = 1 << 6
CAPS0_FRAME_CRC = 1 << 7
CAPS1_VERIFY_READBACK = 1 << 0
CAPS1_CLEAR_ERROR = 1 << 1
CAPS1_DEBUG = 1 << 2
CAPS1_SD_INFO = 1 << 3
CAPS1_SD_INIT = 1 << 4
CAPS1_SD_READ16 = 1 << 5
CAPS1_SD_INSTALL = 1 << 6
CAPS1_SD_WRITE512 = 1 << 7


# ---------------------------------------------------------------------------
# Debug flags (DEBUG response)
# ---------------------------------------------------------------------------

DEBUG_FLAG_RX_ACTIVE = 1 << 0
DEBUG_FLAG_SPI_BUSY = 1 << 1
DEBUG_FLAG_RESP_PENDING = 1 << 2
DEBUG_FLAG_LAST_ERROR = 1 << 3
DEBUG_FLAG_SD_BUSY = 1 << 4
DEBUG_FLAG_AUTO_ACTIVE = 1 << 5
DEBUG_FLAG_AUTO_FALLBACK = 1 << 6
DEBUG_FLAG_SD_PRESENT = 1 << 7


# ---------------------------------------------------------------------------
# Name-lookup functions
# ---------------------------------------------------------------------------

def command_name(command: int) -> str:
    names = {
        CMD_HELLO: "HELLO",
        CMD_PING: "PING",
        CMD_ENTER_SERVICE: "ENTER_SERVICE",
        CMD_UNLOCK: "UNLOCK",
        CMD_EXIT_SERVICE: "EXIT_SERVICE",
        CMD_UPTIME: "UPTIME",
        CMD_IDENTITY: "IDENTITY",
        CMD_PROGRAM16: "PROGRAM16",
        CMD_STATUS: "STATUS",
        CMD_READ16: "READ16",
        CMD_INFO: "INFO",
        CMD_JEDEC: "JEDEC",
        CMD_ERASE64: "ERASE64",
        CMD_LAST_ERROR: "LAST_ERROR",
        CMD_STATS: "STATS",
        CMD_CLEAR_ERROR: "CLEAR_ERROR",
        CMD_DEBUG: "DEBUG",
        CMD_SD_INFO: "SD_INFO",
        CMD_SD_INIT: "SD_INIT",
        CMD_SD_READ16: "SD_READ16",
        CMD_SD_INSTALL: "SD_INSTALL",
        CMD_SD_CRC32_RANGE: "SD_CRC32_RANGE",
        CMD_SD_CRC32: "SD_CRC32",
        CMD_SD_WRITE512: "SD_WRITE512",
        CMD_SDRAM_INFO: "SDRAM_INFO",
        CMD_SDRAM_READ16: "SDRAM_READ16",
        CMD_SDRAM_WRITE16: "SDRAM_WRITE16",
        CMD_SDRAM_TO_FLASH: "SDRAM_TO_FLASH",
        CMD_SDRAM_WRITE_STREAM: "SDRAM_WRITE_STREAM",
        CMD_SDRAM_VERIFY_FLASH: "SDRAM_VERIFY_FLASH",
        CMD_SW_RESET: "SW_RESET",
        CMD_SET_WATCHDOG: "SET_WATCHDOG",
        CMD_RAW_WRITE: "RAW_WRITE",
        CMD_RAW_READ: "RAW_READ",
    }
    return names.get(command, f"0x{command:02X}")


def error_name(code: int) -> str:
    names = {
        0: "clear",
        ERR_UNKNOWN_CMD: "unknown_command",
        ERR_BAD_PROG_LEN: "bad_program_length",
        ERR_BAD_ALIGN: "bad_alignment",
        ERR_RX_TIMEOUT: "rx_timeout",
        ERR_SPI: "spi_failure",
        ERR_BUSY: "busy",
        ERR_SD: "sd_failure",
        ERR_BUNDLE: "bundle_invalid",
        ERR_VERIFY: "verify_failed",
    }
    return names.get(code, f"error_{code}")


def _load_service_state_names() -> dict[int, str]:
    """Parse the service FSM state localparams from rime_service.sv.

    Returns a dict mapping state ordinal -> lower-case state name
    (S_IDLE -> "idle", S_WAIT_SPI -> "wait_spi", etc.). This is
    single-sourced at import time so the decoder cannot drift from
    the firmware.
    """
    import re
    from pathlib import Path

    candidate = Path(__file__).resolve().parent.parent / "firmware" / "images" / "rime" / "rime_service.sv"
    if not candidate.is_file():
        return {}
    text = candidate.read_text(encoding="utf-8", errors="ignore")
    # Match lines like: localparam [4:0] S_IDLE = 5'd0;
    # This regex is tightly scoped to avoid false positives from non-state localparams.
    pattern = re.compile(r"localparam\s+\[\d+:\d+\]\s+S_(\w+)\s*=\s*\d+'d(\d+)\s*;")
    names: dict[int, str] = {}
    for match in pattern.finditer(text):
        label = match.group(1).lower()
        value = int(match.group(2))
        names.setdefault(value, label)
    return names


_SERVICE_STATE_NAMES = _load_service_state_names()


def service_state_name(state: int) -> str:
    """Return the human-readable name for a service FSM state ordinal.

    The name table is parsed from ``firmware/images/rime/rime_service.sv``
    at import time, so host and firmware state names cannot drift.
    Falls back to ``state_N`` if the table is empty (e.g. running
    outside a checkout).
    """
    name = _SERVICE_STATE_NAMES.get(state)
    if name is not None:
        return name
    return f"state_{state}"


def spi_op_name(op: int) -> str:
    names = {0: "none", 1: "jedec", 2: "status", 3: "read16", 4: "erase64", 5: "program16", 6: "crc32_16n"}
    return names.get(op, f"op_{op}")


def sd_error_name(code: int) -> str:
    names = {
        0x00: "clear", 0x01: "no_media", 0x02: "timeout",
        0x03: "cmd0_failed", 0x04: "cmd8_failed", 0x05: "acmd41_failed",
        0x06: "cmd58_failed", 0x07: "reserved_07", 0x08: "cmd17_failed",
        0x09: "data_token_timeout", 0x0A: "bad_chunk", 0x0B: "sd_r1_error",
        0x0C: "cmd24_failed", 0x0D: "data_response_reject",
        0x0E: "write_busy_timeout",
    }
    return names.get(code, f"sd_error_{code}")


def bundle_error_name(code: int) -> str:
    names = {
        0x00: "clear", 0x01: "bad_magic", 0x02: "reserved",
        0x03: "bad_block_size", 0x04: "bad_image_offset",
        0x05: "bad_image_length", 0x06: "bad_padding",
        0x07: "bad_target_address", 0x08: "bad_reserved_bytes",
        0x09: "out_of_range", 0x0A: "unsafe_live_target",
    }
    return names.get(code, f"bundle_error_{code}")


def verify_error_name(code: int) -> str:
    names = {0x00: "clear", 0x01: "readback_mismatch", 0x02: "source_crc_mismatch"}
    return names.get(code, f"verify_error_{code}")


def auto_progress_text(aux0: int, aux1: int) -> str:
    trace_names = {
        1: "ctrl_read", 2: "validate", 3: "prep_running",
        4: "write_running", 5: "running_persisted", 6: "install_begin",
        7: "install_header", 8: "install_read", 9: "install_verify",
        10: "stage_success", 11: "stage_fail", 12: "final_write",
        13: "final_verify", 14: "final_confirm", 15: "done", 16: "exit",
    }
    if aux0 in trace_names:
        return f"phase={trace_names[aux0]} detail=0x{aux1:08X}"
    return f"chunk={aux0} addr=0x{aux1:08X}"


def debug_flag_names(flags: int) -> list[str]:
    names: list[str] = []
    if flags & DEBUG_FLAG_RX_ACTIVE:
        names.append("rx_active")
    if flags & DEBUG_FLAG_SPI_BUSY:
        names.append("spi_busy")
    if flags & DEBUG_FLAG_RESP_PENDING:
        names.append("resp_pending")
    if flags & DEBUG_FLAG_LAST_ERROR:
        names.append("last_error")
    if flags & DEBUG_FLAG_SD_BUSY:
        names.append("sd_busy")
    if flags & DEBUG_FLAG_AUTO_ACTIVE:
        names.append("auto_active")
    if flags & DEBUG_FLAG_AUTO_FALLBACK:
        names.append("auto_fallback")
    if flags & DEBUG_FLAG_SD_PRESENT:
        names.append("sd_present")
    if not names:
        names.append("clear")
    return names


def auto_state_name(state: int) -> str:
    names = {
        0: "start", 1: "wait_init", 2: "read_ctrl", 3: "validate",
        4: "write_running", 5: "install", 6: "write_final", 7: "done",
        8: "prep_running", 9: "retry_init", 10: "hold", 11: "confirm_final",
    }
    return names.get(state, f"auto_state_{state}")


def auto_exit_reason_name(reason: int, detail: int = 0) -> str:
    if reason == 0:
        return "clear"
    if reason == 1:
        return "startup_disabled"
    if reason == 2:
        return "no_media"
    if reason == 3:
        return f"init_failed/{sd_error_name(detail)}"
    if reason == 4:
        return f"ctrl_read_failed/{sd_error_name(detail)}"
    if reason == 5:
        detail_names = {0: "valid", 1: "bad_magic", 2: "reserved", 3: "bad_checksum"}
        return f"ctrl_invalid/{detail_names.get(detail, f'unknown_{detail}')}"
    if reason == 6:
        return "not_armed"
    if reason == 7:
        return "no_bundle"
    if reason == 8:
        return "running_primary"
    if reason == 9:
        return "running_fallback"
    if reason == 10:
        return f"running_write_failed/{sd_error_name(detail)}"
    if reason == 11:
        return "exhausted"
    if reason == 12:
        return "progress_timeout"
    if reason == 13:
        if detail == 0x80:
            return "final_persist_failed/verify_mismatch"
        if detail == 0x81:
            return "final_persist_failed/verify_read_failed"
        if detail == 0x82:
            return "final_persist_failed/late_mismatch"
        if detail == 0x83:
            return "final_persist_failed/late_read_failed"
        return f"final_persist_failed/{sd_error_name(detail)}"
    return f"auto_exit_{reason}/detail_{detail}"


def auto_result_name(result: int) -> str:
    names = {
        0: "none", 1: "pending", 2: "running-primary", 3: "running-fallback",
        4: "success-primary", 5: "success-fallback", 6: "fail-primary",
        7: "fail-fallback", 8: "exhausted", 9: "invalid",
    }
    return names.get(result, f"auto_result_{result}")


def describe_state_code(state_code: int) -> str:
    state = (state_code >> 8) & 0x1F
    addr_index = (state_code >> 5) & 0x03
    data_index = state_code & 0x1F
    return (
        f"{service_state_name(state)}"
        f"/addr={addr_index}/data={data_index}"
        f" (0x{state_code:04X})"
    )
