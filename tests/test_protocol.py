"""Tests for FlashService protocol client using a mock serial port."""

from __future__ import annotations


from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from icepi.flash_service import (
    CMD_CLEAR_ERROR,
    CMD_ENTER_SERVICE,
    CMD_INFO,
    CMD_JEDEC,
    CMD_LAST_ERROR,
    CMD_PING,
    CMD_PROGRAM16,
    CMD_READ16,
    CMD_SD_INFO,
    CMD_STATS,
    CMD_STATUS,
    CMD_UNLOCK,
    CMD_HELLO,
    ERR_SPI,
    MODE_APP,
    MODE_SERVICE,
    PING_REPLY,
    RESP_ERROR,
    FlashService,
    FlashServiceProtocolError,
    FlashServiceRemoteError,
    FlashServiceTimeout,
    crc8,
)


def _frame(payload: bytes, ftype: int = 0x01) -> bytes:
    """Wrap *payload* in the length-prefixed response frame the firmware emits."""
    body = bytes([ftype, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]) + payload
    return body + bytes([crc8(body)])


class MockSerial:
    """Minimal mock of pyserial's Serial, with a response queue."""

    def __init__(self) -> None:
        self._rx_buf = bytearray()
        self._tx_log: list[bytes] = []
        self._responses: list[bytes] = []
        self.dtr = False
        self.rts = False
        self.is_open = True

    @property
    def in_waiting(self) -> int:
        return len(self._rx_buf)

    def write(self, data: bytes) -> int:
        self._tx_log.append(bytes(data))
        if self._responses:
            self._rx_buf.extend(self._responses.pop(0))
        return len(data)

    def read(self, size: int = 1) -> bytes:
        chunk = bytes(self._rx_buf[:size])
        self._rx_buf = self._rx_buf[size:]
        return chunk

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self._rx_buf.clear()

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    def queue(self, *responses: bytes) -> None:
        """Queue response payloads, each wrapped in a length-prefixed frame."""
        self._responses.extend(_frame(r) for r in responses)

    def queue_raw(self, *responses: bytes) -> None:
        """Queue raw wire bytes verbatim (for malformed-frame tests)."""
        self._responses.extend(responses)

    @property
    def last_tx(self) -> bytes:
        return self._tx_log[-1] if self._tx_log else b""


class FragmentedMockSerial(MockSerial):
    """MockSerial that delivers response bytes one at a time, like real silicon
    on a busy USB serial driver. The length-prefixed reader must reassemble a
    frame correctly even when each read() returns a single byte. The plain
    MockSerial returns whole queued chunks atomically and cannot reproduce that
    class of bug. This subclass delivers exactly one byte per read() call
    (cure list item #17).
    """

    def read(self, size: int = 1) -> bytes:
        if not self._rx_buf:
            return b""
        # Always return at most one byte regardless of requested size
        chunk = bytes(self._rx_buf[:1])
        self._rx_buf = self._rx_buf[1:]
        return chunk

    @property
    def in_waiting(self) -> int:
        # Report 1 if anything queued, never the full buffer length —
        # forces the host's _read_frame loop to keep iterating.
        return 1 if self._rx_buf else 0


def _make_service(mock: MockSerial) -> FlashService:
    """Build a FlashService wired to the mock, bypassing real serial open."""
    svc = FlashService.__new__(FlashService)
    svc.port_name = "MOCK"
    svc.target = None
    svc.baud = 115200
    svc.timeout = 0.5
    svc.idle_gap = 0.002
    svc.trace = False
    svc.logger = None
    svc._serial = mock
    svc._erase_cmd = 0x75
    svc._info_cache = None
    svc._sd_crc32_supported = None
    svc._sd_crc32_range_supported = None
    svc._seq = 0
    return svc


# ---------------------------------------------------------------------------
# VERSION
# ---------------------------------------------------------------------------

def test_mode_service():
    mock = MockSerial()
    mock.queue(bytes([CMD_HELLO, MODE_SERVICE]))
    svc = _make_service(mock)
    assert svc.mode() == MODE_SERVICE


def test_mode_app():
    mock = MockSerial()
    mock.queue(bytes([CMD_HELLO, MODE_APP]))
    svc = _make_service(mock)
    assert svc.mode() == MODE_APP


# ---------------------------------------------------------------------------
# PING
# ---------------------------------------------------------------------------

def test_ping_ok():
    mock = MockSerial()
    mock.queue(bytes([CMD_PING, PING_REPLY]))
    svc = _make_service(mock)
    assert svc.ping()


def test_ping_bad():
    mock = MockSerial()
    mock.queue(bytes([CMD_PING, 0x00]))
    svc = _make_service(mock)
    assert not svc.ping()


# ---------------------------------------------------------------------------
# JEDEC
# ---------------------------------------------------------------------------

def test_jedec():
    mock = MockSerial()
    mock.queue(bytes([CMD_JEDEC, 0xEF, 0x40, 0x18]))
    svc = _make_service(mock)
    result = svc.jedec()
    assert result == (0xEF, 0x40, 0x18)


# ---------------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------------

def test_status():
    mock = MockSerial()
    mock.queue(bytes([CMD_STATUS, 0x00, 0x02]))
    svc = _make_service(mock)
    sr1, sr2 = svc.status()
    assert sr1 == 0x00
    assert sr2 == 0x02


# ---------------------------------------------------------------------------
# INFO
# ---------------------------------------------------------------------------

def test_info():
    mock = MockSerial()
    mock.queue(bytes([CMD_INFO, 0x7F, 0xFF, 16, 16, 16, 8, 3]))
    svc = _make_service(mock)
    info = svc.info()
    assert info.max_program == 16
    assert info.read_chunk == 16
    assert info.erase_size == 65536
    assert info.page_size == 256
    assert info.addr_bytes == 3
    assert "read16" in info.caps
    assert "sd_install" in info.caps


# ---------------------------------------------------------------------------
# LAST_ERROR
# ---------------------------------------------------------------------------

def test_last_error_clear():
    mock = MockSerial()
    mock.queue(bytes([CMD_LAST_ERROR, 0, 0, 0, 0, 0, 0]))
    svc = _make_service(mock)
    err = svc.last_error()
    assert not err.valid
    assert err.code == 0


def test_last_error_set():
    mock = MockSerial()
    mock.queue(bytes([CMD_LAST_ERROR, ERR_SPI, CMD_PROGRAM16, 0x05, 0x00, 0x09, 1]))
    svc = _make_service(mock)
    err = svc.last_error()
    assert err.valid
    assert err.code == ERR_SPI
    assert err.command == CMD_PROGRAM16


# ---------------------------------------------------------------------------
# STATS
# ---------------------------------------------------------------------------

def test_stats():
    mock = MockSerial()
    mock.queue(bytes([CMD_STATS, 0, 42, 0, 3, 0, 100, 0, 1]))
    svc = _make_service(mock)
    stats = svc.stats()
    assert stats.command_count == 42
    assert stats.erase_count == 3
    assert stats.program_count == 100
    assert stats.error_count == 1


# ---------------------------------------------------------------------------
# CLEAR_ERROR
# ---------------------------------------------------------------------------

def test_clear_error():
    mock = MockSerial()
    mock.queue(bytes([CMD_CLEAR_ERROR, PING_REPLY]))
    svc = _make_service(mock)
    svc.clear_last_error()  # should not raise


# ---------------------------------------------------------------------------
# READ16
# ---------------------------------------------------------------------------

def test_read16():
    mock = MockSerial()
    payload = bytes([CMD_READ16]) + bytes(range(16))
    mock.queue(payload)
    svc = _make_service(mock)
    data = svc.read16(0x001000)
    assert data == bytes(range(16))
    assert mock.last_tx[0] == CMD_READ16
    assert mock.last_tx[1:4] == bytes([0x00, 0x10, 0x00])


# ---------------------------------------------------------------------------
# ENTER_SERVICE
# ---------------------------------------------------------------------------

def test_enter_service():
    mock = MockSerial()
    mock.queue(bytes([CMD_ENTER_SERVICE, PING_REPLY]))
    mock.queue(bytes([CMD_HELLO, MODE_SERVICE]))
    svc = _make_service(mock)
    assert svc.enter_service_mode() == MODE_SERVICE


# ---------------------------------------------------------------------------
# Error frame
# ---------------------------------------------------------------------------

def test_remote_error():
    mock = MockSerial()
    mock.queue(bytes([RESP_ERROR, ERR_SPI, 0x00, 0x07, CMD_READ16, 0x05, 0x02, 0x03]))
    svc = _make_service(mock)
    try:
        svc.jedec()
        assert False, "should have raised"
    except FlashServiceRemoteError as exc:
        assert exc.code == ERR_SPI
        assert exc.command == CMD_READ16
        assert exc.detail == 0x05


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

def test_timeout():
    mock = MockSerial()
    # Queue nothing — should timeout
    svc = _make_service(mock)
    svc.timeout = 0.05
    try:
        svc.mode()
        assert False, "should have raised"
    except FlashServiceTimeout:
        pass


# ---------------------------------------------------------------------------
# SD_INFO
# ---------------------------------------------------------------------------

def test_sd_info():
    mock = MockSerial()
    flags = 0x07  # present + initialized + high_capacity
    # Bytes 6-9 are SD master debug fields (dbg_state, dbg_shift_in,
    # dbg_shift_busy, svc_state) — see SdInfo docstring and cure list #13.
    mock.queue(bytes([CMD_SD_INFO, flags, 0x00, 0x00, 16, 32, 8, 0xFE, 0, 12]))
    svc = _make_service(mock)
    info = svc.sd_info()
    assert info.card_present
    assert info.initialized
    assert info.high_capacity
    assert info.dbg_state == 8
    assert info.dbg_shift_in == 0xFE
    assert info.dbg_shift_busy == 0
    assert info.svc_state == 12


# ---------------------------------------------------------------------------
# PROBE (service mode)
# ---------------------------------------------------------------------------

def test_probe_service():
    mock = MockSerial()
    # mode -> service
    mock.queue(bytes([CMD_HELLO, MODE_SERVICE]))
    # info
    mock.queue(bytes([CMD_INFO, 0x7F, 0xFF, 16, 16, 16, 8, 3]))
    # last_error
    mock.queue(bytes([CMD_LAST_ERROR, 0, 0, 0, 0, 0, 0]))
    # stats
    mock.queue(bytes([CMD_STATS, 0, 10, 0, 0, 0, 0, 0, 0]))
    # sd_info
    mock.queue(bytes([CMD_SD_INFO, 0x03, 0x00, 0x00, 16, 32, 0, 0, 0, 0]))
    svc = _make_service(mock)
    snapshot = svc.probe(auto_enter=False)
    assert snapshot.mode == "service"
    assert snapshot.info is not None


def test_probe_app():
    mock = MockSerial()
    mock.queue(bytes([CMD_HELLO, MODE_APP]))
    svc = _make_service(mock)
    snapshot = svc.probe(auto_enter=False)
    assert snapshot.mode == "app"


# ---------------------------------------------------------------------------
# CRC-8
# ---------------------------------------------------------------------------



def test_crc8_empty():
    assert crc8(b"") == 0


def test_crc8_known_vectors():
    # Single byte
    assert crc8(bytes([0x00])) == 0x00
    # CRC-8 with poly 0x07: crc8(b"\x01") should be 0x07
    assert crc8(bytes([0x01])) == 0x07
    # Multi-byte deterministic check
    val = crc8(b"\x70\x00\x10\x00")
    assert 0 <= val <= 255
    # Same input gives same output
    assert crc8(b"\x70\x00\x10\x00") == val


def test_crc8_detects_corruption():
    data = bytes([CMD_HELLO, MODE_SERVICE, 19])
    good_crc = crc8(data)
    corrupted = bytes([CMD_HELLO, MODE_SERVICE, 20])
    assert crc8(corrupted) != good_crc


def test_request_has_no_crc_appended():
    """The host sends raw command bytes; only responses are framed."""
    mock = MockSerial()
    mock.queue(bytes([CMD_PING, PING_REPLY]))
    svc = _make_service(mock)
    assert svc.ping() is True
    assert mock.last_tx == bytes([CMD_PING])


def test_bad_response_crc_rejected():
    mock = MockSerial()
    good = _frame(bytes([CMD_PING, PING_REPLY]))
    bad = good[:-1] + bytes([good[-1] ^ 0xFF])  # corrupt the trailing CRC
    mock.queue_raw(bad)
    svc = _make_service(mock)
    try:
        svc.ping()
        assert False, "should have raised"
    except FlashServiceProtocolError as exc:
        assert "CRC mismatch" in str(exc)


# ---------------------------------------------------------------------------
# UNLOCK
# ---------------------------------------------------------------------------



def test_unlock_accepted():
    mock = MockSerial()
    mock.queue(bytes([CMD_UNLOCK, PING_REPLY]))
    svc = _make_service(mock)
    assert svc.unlock() is True
    assert mock.last_tx == bytes([CMD_UNLOCK, 0x52, 0x49, 0x4D, 0x45])


def test_unlock_rejected_by_old_firmware():
    mock = MockSerial()
    # Old firmware returns unknown-command error
    mock.queue(bytes([RESP_ERROR, 0x01, 0x00, 0x00, CMD_UNLOCK, 0x00, 0x00, 0x00]))
    svc = _make_service(mock)
    assert svc.unlock() is False


def test_unlock_timeout_returns_false():
    mock = MockSerial()
    # No response queued — will timeout
    svc = _make_service(mock)
    svc.timeout = 0.05
    assert svc.unlock() is False


# ---------------------------------------------------------------------------
# Fuzz — random bytes should never crash the protocol parser
# ---------------------------------------------------------------------------


@given(data=st.binary(min_size=1, max_size=32))
@settings(deadline=None, max_examples=20)
def test_fuzz_random_response_no_crash(data):
    """The protocol parser should handle arbitrary response bytes without crashing."""
    mock = MockSerial()
    mock.queue(data)
    svc = _make_service(mock)
    svc.timeout = 0.005
    svc.idle_gap = 0.001
    try:
        svc.mode()
    except (FlashServiceRemoteError, FlashServiceTimeout, FlashServiceProtocolError):
        pass  # expected — random bytes are not valid responses


@given(data=st.binary(min_size=1, max_size=64))
@settings(deadline=None, max_examples=20)
def test_fuzz_random_info_response_no_crash(data):
    """INFO parser should handle arbitrary bytes without crashing."""
    mock = MockSerial()
    mock.queue(data)
    svc = _make_service(mock)
    svc.timeout = 0.005
    svc.idle_gap = 0.001
    try:
        svc.info()
    except (FlashServiceRemoteError, FlashServiceTimeout, FlashServiceProtocolError):
        pass


@given(data=st.binary(min_size=1, max_size=32))
@settings(deadline=None, max_examples=20)
def test_fuzz_random_jedec_response_no_crash(data):
    """JEDEC parser should handle arbitrary bytes without crashing."""
    mock = MockSerial()
    mock.queue(data)
    svc = _make_service(mock)
    svc.timeout = 0.005
    svc.idle_gap = 0.001
    try:
        svc.jedec()
    except (FlashServiceRemoteError, FlashServiceTimeout, FlashServiceProtocolError):
        pass


def test_fragmented_serial_mode():
    """Cure list item #17: HELLO must work when bytes arrive one at a time."""
    mock = FragmentedMockSerial()
    mock.queue(bytes([CMD_HELLO, MODE_SERVICE]))
    svc = _make_service(mock)
    assert svc.mode() == MODE_SERVICE


def test_fragmented_serial_info():
    """Cure list item #17: INFO response must arrive correctly under fragmentation."""
    mock = FragmentedMockSerial()
    mock.queue(bytes([CMD_INFO, 0x7F, 0xFF, 16, 16, 16, 8, 3]))
    svc = _make_service(mock)
    info = svc.info()
    assert info.max_program == 16
    assert info.read_chunk == 16


def test_fragmented_serial_jedec():
    mock = FragmentedMockSerial()
    mock.queue(bytes([CMD_JEDEC, 0xEF, 0x40, 0x18]))
    svc = _make_service(mock)
    assert svc.jedec() == (0xEF, 0x40, 0x18)


def test_fragmented_serial_long_read16():
    """READ16 returns 17 bytes (cmd + 16 data). Fragmented delivery must
    reassemble all 17 payload bytes correctly."""
    from icepi.flash_service import CMD_READ16
    mock = FragmentedMockSerial()
    payload = bytes([CMD_READ16]) + bytes(range(16))
    mock.queue(payload)
    svc = _make_service(mock)
    data = svc.read16(0x001000)
    assert data == bytes(range(16))


def test_fragmented_serial_error_frame():
    """8-byte error frames must reassemble correctly under fragmentation."""
    from icepi.flash_service import CMD_READ16
    mock = FragmentedMockSerial()
    mock.queue(bytes([RESP_ERROR, ERR_SPI, 0x00, 0x07, CMD_READ16, 0x05, 0x02, 0x03]))
    svc = _make_service(mock)
    try:
        svc.jedec()
        assert False, "should have raised"
    except FlashServiceRemoteError as exc:
        assert exc.code == ERR_SPI


@given(data=st.binary(min_size=1, max_size=64))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_fragmented_random_response_no_crash(data):
    """Fuzz: random byte payloads delivered one byte at a time must never crash the parser."""
    mock = FragmentedMockSerial()
    mock.queue(data)
    svc = _make_service(mock)
    svc.timeout = 0.005
    svc.idle_gap = 0.001
    try:
        svc.mode()
    except (FlashServiceRemoteError, FlashServiceTimeout, FlashServiceProtocolError):
        pass


def test_raw_exchange_delegates_to_private():
    """Cure list item #12: raw_exchange is the public form of _exchange.
    Sending the same payload through both must produce the same result."""
    from icepi.flash_service import CMD_PING
    mock = MockSerial()
    mock.queue(bytes([CMD_PING, PING_REPLY]))
    svc = _make_service(mock)
    frame = svc.raw_exchange(bytes([CMD_PING]), timeout=1.0)
    assert frame == bytes([CMD_PING, PING_REPLY])


def test_command_name_covers_all_defined_commands():
    """Every CMD_* constant must have an entry in command_name()."""
    from icepi import flash_service as fs

    missing = []
    for attr in dir(fs):
        if not attr.startswith("CMD_"):
            continue
        value = getattr(fs, attr)
        if not isinstance(value, int):
            continue
        name = fs.command_name(value)
        if name == f"0x{value:02X}":
            missing.append((attr, value))
    assert missing == [], f"command_name() missing entries: {missing}"


def test_flash_service_public_api_stable():
    """Pin the public API surface of flash_service to catch accidental breakage during refactors."""
    from icepi import flash_service as fs

    required_classes = [
        "BoardTarget", "DeviceSnapshot", "FlashService",
        "FlashServiceDiscoveryError", "FlashServiceError",
        "FlashServiceProtocolError", "FlashServiceRemoteError",
        "FlashServiceTimeout", "FlashServiceVerifyError",
        "SdInfo", "ServiceDebug", "ServiceInfo", "ServiceLastError",
        "ServiceSnapshot", "ServiceStats", "UploadResult",
    ]
    required_constants = [
        "CMD_HELLO", "CMD_PING", "CMD_ENTER_SERVICE", "CMD_UNLOCK",
        "CMD_EXIT_SERVICE", "CMD_UPTIME", "CMD_IDENTITY",
        "CMD_PROGRAM16", "CMD_STATUS", "CMD_READ16", "CMD_INFO",
        "CMD_JEDEC", "CMD_ERASE64", "CMD_LAST_ERROR", "CMD_STATS",
        "CMD_CLEAR_ERROR", "CMD_DEBUG", "CMD_SD_INFO", "CMD_SD_INIT",
        "CMD_SD_READ16", "CMD_SD_INSTALL", "CMD_SD_CRC32",
        "CMD_SD_CRC32_RANGE", "CMD_SD_WRITE512",
        "CMD_SDRAM_INFO", "CMD_SDRAM_READ16", "CMD_SDRAM_WRITE16",
        "CMD_SDRAM_TO_FLASH", "CMD_SDRAM_WRITE_STREAM",
        "CMD_SDRAM_VERIFY_FLASH", "CMD_SW_RESET", "CMD_SET_WATCHDOG",
        "CMD_RAW_WRITE", "CMD_RAW_READ",
        "ERR_UNKNOWN_CMD", "ERR_BAD_PROG_LEN", "ERR_BAD_ALIGN",
        "ERR_RX_TIMEOUT", "ERR_SPI", "ERR_BUSY", "ERR_SD",
        "ERR_BUNDLE", "ERR_VERIFY",
        "CAPS0_READ16", "CAPS0_ERASE64", "CAPS0_PROGRAM16",
        "CAPS0_STATUS", "CAPS0_INFO", "CAPS0_LAST_ERROR",
        "CAPS0_STATS",
        "CAPS1_VERIFY_READBACK", "CAPS1_CLEAR_ERROR", "CAPS1_DEBUG",
        "CAPS1_SD_INFO", "CAPS1_SD_INIT", "CAPS1_SD_READ16",
        "CAPS1_SD_INSTALL", "CAPS1_SD_WRITE512",
        "RESP_ERROR", "PING_REPLY",
        "MODE_SERVICE", "MODE_APP_STARTUP", "MODE_APP_FAILSAFE",
    ]
    required_functions = [
        "crc8", "command_name", "error_name", "service_state_name",
        "spi_op_name", "sd_error_name", "bundle_error_name",
        "verify_error_name", "auto_state_name", "auto_exit_reason_name",
        "auto_result_name", "auto_progress_text", "debug_flag_names",
        "describe_state_code", "find_device_port", "list_matching_ports",
        "load_board_target", "probe_device", "resolve_board_target",
        "resolve_board_target_from_args",
        "is_startup_recovery_mode", "is_startup_failsafe_mode",
    ]

    missing = []
    for name in required_classes + required_constants + required_functions:
        if not hasattr(fs, name):
            missing.append(name)
    assert missing == [], f"flash_service lost public symbols: {missing}"
