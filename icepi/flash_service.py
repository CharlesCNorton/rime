"""UART transport client for the IcePi Zero resident flash/SD service.

Handles board discovery, serial protocol framing, and all flash and SD
commands exposed by the on-board service firmware.  The primary entry
point is the :class:`FlashService` context manager.
"""

from __future__ import annotations

import binascii
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal

__all__ = [
    "BoardTarget",
    "DeviceSnapshot",
    "FlashService",
    "crc8",
    "FlashServiceDiscoveryError",
    "FlashServiceError",
    "FlashServiceProtocolError",
    "FlashServiceRemoteError",
    "FlashServiceTimeout",
    "FlashServiceVerifyError",
    "LogCallback",
    "ProgressCallback",
    "SdInfo",
    "SdramInfo",
    "ServiceDebug",
    "ServiceInfo",
    "ServiceLastError",
    "ServiceSnapshot",
    "ServiceStats",
    "UploadResult",
    "find_device_port",
    "list_matching_ports",
    "load_board_target",
    "probe_device",
    "resolve_board_target",
    "resolve_board_target_from_args",
]

from icepi.tools import REPO_ROOT, pip_install_hint, strip_bitstream_header  # noqa: E402
from icepi.protocol import *  # noqa: F401,F403 — re-export for backwards compatibility
from icepi.protocol import (  # noqa: F811 — explicit imports for local use
    crc8,
    CMD_HELLO, CMD_PING, CMD_ENTER_SERVICE, CMD_UNLOCK,
    CMD_EXIT_SERVICE, CMD_UPTIME, CMD_IDENTITY,
    CMD_SD_CRC32_RANGE, CMD_PROGRAM16, CMD_STATUS, CMD_READ16,
    CMD_INFO, CMD_JEDEC, CMD_ERASE64, CMD_LAST_ERROR, CMD_STATS,
    CMD_CLEAR_ERROR, CMD_DEBUG,
    CMD_SD_INFO, CMD_SD_INIT, CMD_SD_READ16, CMD_SD_INSTALL,
    CMD_SD_CRC32, CMD_SD_WRITE512,
    CMD_SDRAM_INFO, CMD_SDRAM_READ16, CMD_SDRAM_WRITE16,
    CMD_SDRAM_TO_FLASH, CMD_SDRAM_WRITE_STREAM, CMD_SDRAM_VERIFY_FLASH,
    CMD_SW_RESET, CMD_SET_WATCHDOG,
    RESP_ERROR, PING_REPLY,
    MODE_SERVICE, MODE_APP_STARTUP, MODE_APP_FAILSAFE,
    ERR_UNKNOWN_CMD, ERR_SD, ERR_BUNDLE, ERR_VERIFY,
    CAPS0_READ16, CAPS0_ERASE64, CAPS0_PROGRAM16, CAPS0_STATUS,
    CAPS0_INFO, CAPS0_LAST_ERROR, CAPS0_STATS,
    CAPS1_VERIFY_READBACK, CAPS1_CLEAR_ERROR, CAPS1_DEBUG,
    CAPS1_SD_INFO, CAPS1_SD_INIT, CAPS1_SD_READ16,
    CAPS1_SD_INSTALL, CAPS1_SD_WRITE512,
    command_name, error_name, service_state_name, spi_op_name,
    sd_error_name, bundle_error_name, verify_error_name,
    auto_state_name, auto_exit_reason_name, auto_result_name,
    auto_progress_text, debug_flag_names, describe_state_code,
)

DEFAULT_BAUD = 115200
BOARD_LOCAL_CONFIG = REPO_ROOT / "config" / "board.local.json"

# Addressable range limits. Flash and SDRAM both use 24-bit addressing on
# IcePi Zero: flash is 16 MiB byte-addressed (W25Q128), SDRAM is 32 MiB
# word-addressed (16 Mi 16-bit words). Reads near the end of either device
# wrap at the chip boundary on silicon — every host access is clamped here
# so accidental wrap becomes an explicit error instead of a silent data mix.
FLASH_SIZE_BYTES = 0x01000000   # 16 MiB W25Q128
SDRAM_WORD_COUNT = 0x01000000   # 16 Mi words = 32 MiB (16-bit words)


def _check_flash_window(label: str, address: int, length: int) -> None:
    if address < 0:
        raise FlashServiceError(f"{label}: address must be non-negative, got {address}")
    if length < 0:
        raise FlashServiceError(f"{label}: length must be non-negative, got {length}")
    if address + length > FLASH_SIZE_BYTES:
        raise FlashServiceError(
            f"{label}: range 0x{address:06X}..0x{address + length - 1:06X} "
            f"crosses flash end (0x{FLASH_SIZE_BYTES:06X}) — wrap is not allowed"
        )


def _check_sdram_word_window(label: str, word_address: int, word_count: int) -> None:
    if word_address < 0:
        raise FlashServiceError(f"{label}: word address must be non-negative, got {word_address}")
    if word_count < 0:
        raise FlashServiceError(f"{label}: word count must be non-negative, got {word_count}")
    if word_address + word_count > SDRAM_WORD_COUNT:
        raise FlashServiceError(
            f"{label}: word range 0x{word_address:06X}..0x{word_address + word_count - 1:06X} "
            f"crosses SDRAM end (0x{SDRAM_WORD_COUNT:06X}) — wrap is not allowed"
        )


def _parse_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text, 0)


def _parse_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(slots=True)
class BoardTarget:
    config_path: Path | None = None
    usb_instance: str | None = None
    usb_vid: int | None = None
    usb_pid: int | None = None
    usb_serial: str | None = None
    baud: int = DEFAULT_BAUD

    def merge(
        self,
        *,
        config_path: Path | None = None,
        usb_instance: str | None = None,
        usb_vid: int | None = None,
        usb_pid: int | None = None,
        usb_serial: str | None = None,
        baud: int | None = None,
    ) -> "BoardTarget":
        return BoardTarget(
            config_path=config_path or self.config_path,
            usb_instance=usb_instance if usb_instance is not None else self.usb_instance,
            usb_vid=usb_vid if usb_vid is not None else self.usb_vid,
            usb_pid=usb_pid if usb_pid is not None else self.usb_pid,
            usb_serial=usb_serial if usb_serial is not None else self.usb_serial,
            baud=self.baud if baud is None else baud,
        )

    def has_identity_hints(self) -> bool:
        return any(
            value is not None
            for value in (self.usb_instance, self.usb_vid, self.usb_pid, self.usb_serial)
        )

    def identity_label(self) -> str:
        parts: list[str] = []
        if self.usb_instance:
            parts.append(f"instance={self.usb_instance}")
        if self.usb_vid is not None:
            parts.append(f"vid=0x{self.usb_vid:04X}")
        if self.usb_pid is not None:
            parts.append(f"pid=0x{self.usb_pid:04X}")
        if self.usb_serial:
            parts.append(f"serial={self.usb_serial}")
        if not parts:
            return "no board identity hints configured"
        return ", ".join(parts)

    def as_dict(self) -> dict[str, object]:
        return {
            "config_path": str(self.config_path) if self.config_path else None,
            "usb_instance": self.usb_instance,
            "usb_vid": self.usb_vid,
            "usb_pid": self.usb_pid,
            "usb_serial": self.usb_serial,
            "baud": self.baud,
        }


@dataclass(slots=True)
class DeviceSnapshot:
    present: bool
    mode: str
    driver: str | None
    friendly_name: str | None
    service: str | None
    instance_id: str | None
    com_port: str | None
    notes: list[str]


def _load_json_file(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"board config must be a JSON object: {path}")
    return data


def find_board_config(path: str | Path | None = None) -> Path | None:
    if path is not None:
        candidate = Path(path).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate

    env_path = os.environ.get("ICEPI_BOARD_CONFIG")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate

    if BOARD_LOCAL_CONFIG.exists():
        return BOARD_LOCAL_CONFIG
    return None


def load_board_target(path: str | Path | None = None) -> BoardTarget:
    config_path = find_board_config(path)
    raw: dict[str, object] = {}
    if config_path is not None:
        raw = _load_json_file(config_path)
    target = BoardTarget(
        config_path=config_path,
        usb_instance=_parse_optional_str(raw.get("usb_instance")),
        usb_vid=_parse_optional_int(raw.get("usb_vid")),
        usb_pid=_parse_optional_int(raw.get("usb_pid")),
        usb_serial=_parse_optional_str(raw.get("usb_serial")),
        baud=_parse_optional_int(raw.get("baud")) or DEFAULT_BAUD,
    )
    env_instance = _parse_optional_str(os.environ.get("ICEPI_USB_INSTANCE"))
    env_vid = _parse_optional_int(os.environ.get("ICEPI_USB_VID"))
    env_pid = _parse_optional_int(os.environ.get("ICEPI_USB_PID"))
    env_serial = _parse_optional_str(os.environ.get("ICEPI_USB_SERIAL"))
    env_baud = _parse_optional_int(os.environ.get("ICEPI_BAUD"))
    return target.merge(
        usb_instance=env_instance,
        usb_vid=env_vid,
        usb_pid=env_pid,
        usb_serial=env_serial,
        baud=env_baud,
    )


def resolve_board_target(
    *,
    path: str | Path | None = None,
    usb_instance: str | None = None,
    usb_vid: int | str | None = None,
    usb_pid: int | str | None = None,
    usb_serial: str | None = None,
    baud: int | None = None,
) -> BoardTarget:
    target = load_board_target(path)
    return target.merge(
        usb_instance=_parse_optional_str(usb_instance),
        usb_vid=_parse_optional_int(usb_vid),
        usb_pid=_parse_optional_int(usb_pid),
        usb_serial=_parse_optional_str(usb_serial),
        baud=baud,
    )


def resolve_board_target_from_args(args: object) -> BoardTarget:
    return resolve_board_target(
        path=getattr(args, "board_config", None),
        usb_instance=getattr(args, "usb_instance", None),
        usb_vid=getattr(args, "usb_vid", None),
        usb_pid=getattr(args, "usb_pid", None),
        usb_serial=getattr(args, "usb_serial", None),
        baud=getattr(args, "baud", None),
    )

ProgressCallback = Callable[[str, int, int, str | None], None]
LogCallback = Callable[[str], None]


def _load_pyserial() -> Any:
    try:
        import serial  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"pyserial is required. Install it with: {pip_install_hint('pyserial')}"
        ) from exc
    return serial


def _serial_permission_hint(port: str) -> str:
    """Return a platform-specific hint for a serial-port permission error.

    On POSIX, ``EACCES`` opening a tty almost always means the user is not in
    the group that owns the device node (commonly ``dialout`` on Linux, ``uucp``
    on some distros) rather than a busy port. We stat the node to name the
    actual owning group so the suggested fix is copy-pasteable. On Windows the
    usual cause is another process already holding the COM port.
    """
    if os.name == "nt":
        return (
            "another process may be holding the port (close any open serial "
            "monitor or IDE), or the account lacks permission to access it."
        )
    group = None
    try:
        import grp
        group = grp.getgrgid(os.stat(port).st_gid).gr_name
    except Exception:
        group = None
    grp_name = group or "dialout"
    return (
        f"your user is not in the '{grp_name}' group that owns {port}. "
        f"Add yourself and re-login: `sudo usermod -aG {grp_name} $USER` "
        f"(or activate it in one shell now with `sg {grp_name} -c '<command>'`). "
        f"A stale process holding the port can also cause this."
    )


def _is_permission_error(exc: BaseException) -> bool:
    """Return True if *exc* represents a serial-port permission denial.

    pyserial raises ``serial.SerialException`` with the underlying OS error
    folded into the message rather than surfacing the built-in ``PermissionError``
    type, so a bare ``except PermissionError`` does not catch EACCES on Linux.
    Check the type, the ``errno`` attribute, and the message text.
    """
    import errno as _errno
    if isinstance(exc, PermissionError):
        return True
    if getattr(exc, "errno", None) == _errno.EACCES:
        return True
    msg = str(exc).lower()
    return "permission denied" in msg or "errno 13" in msg or "access is denied" in msg


def _normalize(text: str | None) -> str | None:
    if text is None:
        return None
    value = text.strip()
    return value.upper() if value else None


def _serial_matches(actual: str | None, expected: str | None) -> bool:
    actual_norm = _normalize(actual)
    expected_norm = _normalize(expected)
    if expected_norm is None:
        return True
    if actual_norm is None:
        return False
    return (
        actual_norm == expected_norm
        or actual_norm.startswith(expected_norm)
        or expected_norm.startswith(actual_norm)
    )


def _port_matches_target(port: Any, target: BoardTarget) -> bool:
    vid = getattr(port, "vid", None)
    pid = getattr(port, "pid", None)
    serial_number = getattr(port, "serial_number", None)

    if target.usb_vid is not None and vid != target.usb_vid:
        return False
    if target.usb_pid is not None and pid != target.usb_pid:
        return False
    if not _serial_matches(serial_number, target.usb_serial):
        return False
    return True


def list_matching_ports(target: BoardTarget | None = None) -> list[Any]:
    _load_pyserial()
    try:
        import serial.tools.list_ports as list_ports  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"pyserial is required. Install it with: {pip_install_hint('pyserial')}"
        ) from exc
    resolved = target or resolve_board_target()
    matches: list[Any] = []
    for port in list_ports.comports():
        if _port_matches_target(port, resolved):
            matches.append(port)
    return matches


def _read_length_prefixed(serial_port: Any, *, timeout: float) -> tuple[int, bytes] | None:
    """Read one length-prefixed response frame: ``[type, len_lo, len_hi, payload, crc8]``.

    Returns ``(frame_type, payload)`` with the CRC-8 validated, or ``None`` on
    timeout/truncation. The header gives the exact payload length to read.
    """
    deadline = time.monotonic() + timeout

    def _exact(n: int) -> bytes | None:
        buf = bytearray()
        while len(buf) < n:
            if time.monotonic() > deadline:
                return None
            chunk = serial_port.read(n - len(buf))
            if chunk:
                buf.extend(chunk)
            else:
                time.sleep(0.0005)
        return bytes(buf)

    header = _exact(3)
    if header is None:
        return None
    length = header[1] | (header[2] << 8)
    payload = _exact(length) if length else b""
    if payload is None:
        return None
    crc = _exact(1)
    if crc is None:
        return None
    expected = crc8(header + payload)
    if crc[0] != expected:
        raise FlashServiceProtocolError(
            f"CRC mismatch: received 0x{crc[0]:02X}, expected 0x{expected:02X}"
        )
    return header[0], payload


def _probe_protocol(port_name: str, *, baud: int) -> int | None:
    serial = _load_pyserial()
    try:
        with serial.Serial(
            port=port_name,
            baudrate=baud,
            timeout=0.0,
            write_timeout=1.0,
            inter_byte_timeout=0.0,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
        ) as handle:
            handle.dtr = False
            handle.rts = False
            handle.reset_input_buffer()
            handle.reset_output_buffer()
            time.sleep(0.03)
            handle.write(bytes([CMD_HELLO]))
            handle.flush()
            result = _read_length_prefixed(handle, timeout=0.75)
    except Exception:
        return None

    if result is None:
        return None
    payload = result[1]
    if len(payload) < 2 or payload[0] != CMD_HELLO:
        return None
    mode = payload[1]
    if mode == 0xFF:
        return None
    return mode


def _candidate_label(port: Any) -> str:
    device = getattr(port, "device", None) or "<unknown>"
    description = getattr(port, "description", None)
    serial_number = getattr(port, "serial_number", None)
    parts = [device]
    if description:
        parts.append(description)
    if serial_number:
        parts.append(f"serial={serial_number}")
    return " / ".join(parts)


def find_device_port(
    port: str | None = None,
    *,
    baud: int | None = None,
    target: BoardTarget | None = None,
) -> str | None:
    if port:
        return port

    resolved = target or resolve_board_target(baud=baud)
    effective_baud = baud or resolved.baud
    candidates = list_matching_ports(resolved)
    if not candidates:
        return None

    if resolved.has_identity_hints() and len(candidates) == 1:
        return getattr(candidates[0], "device", None)

    responsive: list[Any] = []
    for candidate in candidates:
        device = getattr(candidate, "device", None)
        if not device:
            continue
        mode = _probe_protocol(device, baud=effective_baud)
        if mode is not None:
            responsive.append(candidate)

    if len(responsive) == 1:
        return getattr(responsive[0], "device", None)
    if len(responsive) > 1:
        labels = ", ".join(_candidate_label(candidate) for candidate in responsive)
        raise RuntimeError(
            "multiple serial ports answered the IcePi protocol; use --port or set board.local.json. "
            f"Candidates: {labels}"
        )

    if resolved.has_identity_hints() and len(candidates) == 1:
        return getattr(candidates[0], "device", None)
    return None


def _port_record_for_device(device_name: str | None) -> Any | None:
    if not device_name:
        return None
    _load_pyserial()
    try:
        import serial.tools.list_ports as list_ports  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"pyserial is required. Install it with: {pip_install_hint('pyserial')}"
        ) from exc
    for port in list_ports.comports():
        if getattr(port, "device", None) == device_name:
            return port
    return None


def probe_device(
    *,
    target: BoardTarget | None = None,
    baud: int | None = None,
) -> DeviceSnapshot:
    resolved = target or resolve_board_target(baud=baud)
    effective_baud = baud or resolved.baud
    notes: list[str] = []
    com_port = None
    port_record = None

    try:
        com_port = find_device_port(baud=effective_baud, target=resolved)
    except RuntimeError as exc:
        notes.append(str(exc))

    if com_port:
        port_record = _port_record_for_device(com_port)

    present = bool(com_port)
    driver = None
    friendly_name = None
    service = None
    instance_id = None
    mode = "missing"

    if com_port:
        friendly_name = getattr(port_record, "description", None) or f"Serial device ({com_port})"
        instance_id = getattr(port_record, "hwid", None)
        serial_number = getattr(port_record, "serial_number", None)
        service = "serial"
        if serial_number:
            service = f"serial={serial_number}"
        mode = "uart"
        driver = "serial"

    if mode == "missing":
        notes.append("IcePi Zero is not present in serial-protocol discovery.")
        if not resolved.has_identity_hints():
            notes.append("Set board.local.json or ICEPI_USB_INSTANCE/ICEPI_USB_SERIAL for more reliable serial-port selection.")
        notes.append("USB-only or JTAG-only presence is host-specific and is not inferred by the core transport layer.")
    if mode == "uart" and com_port:
        notes.append(f"UART is available on {com_port} at {effective_baud} baud.")

    return DeviceSnapshot(
        present=present,
        mode=mode,
        driver=driver,
        friendly_name=friendly_name,
        service=service,
        instance_id=instance_id,
        com_port=com_port,
        notes=notes,
    )


class FlashServiceError(RuntimeError):
    pass


class FlashServiceDiscoveryError(FlashServiceError):
    pass


class FlashServiceTimeout(FlashServiceError):
    pass


class FlashServiceProtocolError(FlashServiceError):
    pass


class FlashServiceRemoteError(FlashServiceError):
    def __init__(
        self,
        code: int,
        state: int,
        command: int,
        detail: int,
        *,
        flags: int | None = None,
        op: int | None = None,
        seq: int | None = None,
    ) -> None:
        self.code = code
        self.state = state
        self.command = command
        self.detail = detail
        self.flags = flags
        self.op = op
        self.seq = seq
        parts = [
            f"FPGA reported {error_name(code)} on {command_name(command)}",
            f"state={describe_state_code(state)}",
            f"detail=0x{detail:02X}",
        ]
        if code == ERR_SD:
            parts[-1] = f"detail={sd_error_name(detail)} (0x{detail:02X})"
        elif code == ERR_BUNDLE:
            parts[-1] = f"detail={bundle_error_name(detail)} (0x{detail:02X})"
        elif code == ERR_VERIFY:
            parts[-1] = f"detail={verify_error_name(detail)} (0x{detail:02X})"
        if flags is not None:
            parts.append("flags=" + ",".join(debug_flag_names(flags)))
        if op is not None:
            parts.append(f"spi_op={spi_op_name(op)}")
        if seq is not None:
            parts.append(f"seq={seq}")
        super().__init__("; ".join(parts))


class FlashServiceVerifyError(FlashServiceError):
    def __init__(self, address: int, expected: bytes, actual: bytes):
        self.address = address
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"readback mismatch at 0x{address:06X}\n"
            f"  expected: {expected.hex(' ')}\n"
            f"  actual:   {actual.hex(' ')}"
        )


@dataclass(slots=True)
class ServiceInfo:
    caps0: int
    caps1: int
    max_program: int
    read_chunk: int
    erase_log2: int
    page_log2: int
    addr_bytes: int

    @property
    def erase_size(self) -> int:
        return 1 << self.erase_log2

    @property
    def page_size(self) -> int:
        return 1 << self.page_log2

    @property
    def caps(self) -> list[str]:
        caps: list[str] = []
        if self.caps0 & CAPS0_READ16:
            caps.append("read16")
        if self.caps0 & CAPS0_ERASE64:
            caps.append("erase64")
        if self.caps0 & CAPS0_PROGRAM16:
            caps.append("program16")
        if self.caps0 & CAPS0_STATUS:
            caps.append("status")
        if self.caps0 & CAPS0_INFO:
            caps.append("info")
        if self.caps0 & CAPS0_LAST_ERROR:
            caps.append("last_error")
        if self.caps0 & CAPS0_STATS:
            caps.append("stats")
        if self.caps1 & CAPS1_VERIFY_READBACK:
            caps.append("verify_readback")
        if self.caps1 & CAPS1_CLEAR_ERROR:
            caps.append("clear_error")
        if self.caps1 & CAPS1_DEBUG:
            caps.append("debug")
        if self.caps1 & CAPS1_SD_INFO:
            caps.append("sd_info")
        if self.caps1 & CAPS1_SD_INIT:
            caps.append("sd_init")
        if self.caps1 & CAPS1_SD_READ16:
            caps.append("sd_read16")
        caps.append("sd_crc32")
        if self.caps1 & CAPS1_SD_INSTALL:
            caps.append("sd_install")
        if self.caps1 & CAPS1_SD_WRITE512:
            caps.append("sd_write512")
        caps.append("sd_autoboot")
        return caps


@dataclass(slots=True)
class ServiceLastError:
    code: int
    command: int
    detail: int
    state: int
    valid: bool

    @property
    def name(self) -> str:
        return error_name(self.code)

    @property
    def detail_name(self) -> str:
        if self.code == ERR_SD:
            return sd_error_name(self.detail)
        if self.code == ERR_BUNDLE:
            return bundle_error_name(self.detail)
        if self.code == ERR_VERIFY:
            return verify_error_name(self.detail)
        return f"0x{self.detail:02X}"


@dataclass(slots=True)
class ServiceStats:
    """Cumulative service statistics returned by :meth:`FlashService.stats`."""

    command_count: int
    erase_count: int
    program_count: int
    error_count: int

    def as_dict(self) -> dict[str, int]:
        """Serialize to a plain dict."""
        return {
            "command_count": self.command_count,
            "erase_count": self.erase_count,
            "program_count": self.program_count,
            "error_count": self.error_count,
        }


@dataclass(slots=True)
class SdInfo:
    """Decoded SD_INFO response. Field names match what the firmware emits.

    The firmware emits (after the cmd echo):
        byte 1: flags     {sd_det_in, high_capacity, initialized, card_present}
        byte 2: last_error
        byte 3: last_r1
        byte 4: chunk_bytes (16)
        byte 5: chunks_per_block (32)
        byte 6: dbg_state       — SD master FSM state (5 bits)
        byte 7: dbg_shift_in    — last shift register byte (debug only)
        byte 8: dbg_shift_busy  — 1 bit
        byte 9: svc_state       — service FSM state at moment of read

    Older versions of the host parser treated bytes 6-9 as `init_count` and
    `read_count` 16-bit counters. That was a contract drift bug — the
    firmware never emitted those counters in this command. The host's
    `SdInfo.init_count` was actually `(dbg_state << 8) | dbg_shift_in`,
    which produced nonsensical oscillating values (cure list item #13).
    """
    flags: int
    last_error: int
    last_r1: int
    chunk_bytes: int
    chunks_per_block: int
    dbg_state: int
    dbg_shift_in: int
    dbg_shift_busy: int
    svc_state: int

    @property
    def card_present(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def initialized(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def high_capacity(self) -> bool:
        return bool(self.flags & 0x04)

    @property
    def detect_low(self) -> bool:
        return bool(self.flags & 0x08)

    @property
    def last_error_name(self) -> str:
        return sd_error_name(self.last_error)


@dataclass(slots=True)
class SdramInfo:
    """Decoded SDRAM_INFO response."""
    init_done: bool
    caps2: int

    @property
    def streaming(self) -> bool:
        return bool(self.caps2 & 0x01)

    @property
    def verify(self) -> bool:
        return bool(self.caps2 & 0x02)

    @property
    def raw_access(self) -> bool:
        return bool(self.caps2 & 0x04)


@dataclass(slots=True)
class ServiceDebug:
    state: int
    current_cmd: int
    spi_op: int
    addr_index: int
    data_index: int
    resp_len: int
    resp_pos: int
    flags: int
    auto_state: int = 0
    auto_exit_reason: int = 0
    auto_exit_detail: int = 0
    auto_init_attempts: int = 0
    auto_aux0: int = 0
    auto_aux1: int = 0
    auto_write_result: int = 0
    auto_write_source_lba: int = 0

    @property
    def state_name(self) -> str:
        return service_state_name(self.state)

    @property
    def current_cmd_name(self) -> str:
        return command_name(self.current_cmd)

    @property
    def spi_op_name(self) -> str:
        return spi_op_name(self.spi_op)

    @property
    def flag_names(self) -> list[str]:
        return debug_flag_names(self.flags)

    @property
    def auto_state_name(self) -> str:
        return auto_state_name(self.auto_state)

    @property
    def auto_exit_reason_name(self) -> str:
        return auto_exit_reason_name(self.auto_exit_reason, self.auto_exit_detail)

    @property
    def auto_progress_text(self) -> str:
        return auto_progress_text(self.auto_aux0, self.auto_aux1)

    @property
    def auto_write_result_name(self) -> str:
        return auto_result_name(self.auto_write_result)


@dataclass(slots=True)
class UploadResult:
    """Result of a :meth:`FlashService.upload_bitstream` operation."""

    base_address: int
    bytes: int
    padded_bytes: int
    erase_size: int
    chunk_size: int


@dataclass(slots=True)
class ServiceSnapshot:
    port: str
    mode: Literal["app", "service", "startup", "failsafe"]
    info: ServiceInfo | None = None
    jedec: tuple[int, int, int] | None = None
    status: tuple[int, int] | None = None
    sd_info: SdInfo | None = None
    last_error: ServiceLastError | None = None
    stats: ServiceStats | None = None
    debug: ServiceDebug | None = None

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        if self.info is not None:
            result["info"] = asdict(self.info)
            result["info"]["caps"] = self.info.caps
        if self.last_error is not None:
            result["last_error"] = asdict(self.last_error)
            result["last_error"]["name"] = self.last_error.name
            result["last_error"]["detail_name"] = self.last_error.detail_name
            result["last_error"]["state_text"] = describe_state_code(self.last_error.state)
        if self.sd_info is not None:
            result["sd_info"] = asdict(self.sd_info)
            result["sd_info"]["card_present"] = self.sd_info.card_present
            result["sd_info"]["initialized"] = self.sd_info.initialized
            result["sd_info"]["high_capacity"] = self.sd_info.high_capacity
            result["sd_info"]["detect_low"] = self.sd_info.detect_low
            result["sd_info"]["last_error_name"] = self.sd_info.last_error_name
        if self.debug is not None:
            result["debug"] = asdict(self.debug)
            result["debug"]["state_name"] = self.debug.state_name
            result["debug"]["current_cmd_name"] = self.debug.current_cmd_name
            result["debug"]["spi_op_name"] = self.debug.spi_op_name
            result["debug"]["flag_names"] = self.debug.flag_names
            result["debug"]["auto_state_name"] = self.debug.auto_state_name
            result["debug"]["auto_exit_reason_name"] = self.debug.auto_exit_reason_name
            result["debug"]["auto_progress_text"] = self.debug.auto_progress_text
        return result


def is_startup_recovery_mode(mode: int) -> bool:
    return mode == MODE_APP_STARTUP


def is_startup_failsafe_mode(mode: int) -> bool:
    return mode == MODE_APP_FAILSAFE


# Name-lookup functions (command_name, error_name, service_state_name, etc.)
# are imported from icepi.protocol and re-exported via the wildcard import above.




class FlashService:
    """UART transport client for the IcePi Zero resident service.

    Wraps a serial connection to the board and exposes every command the
    on-board service firmware supports: flash read/erase/program, JEDEC
    probe, SD card I/O, CRC32 verification, bundle install, and
    auto-recovery control.

    Use as a context manager::

        with FlashService() as svc:
            mfr, dev, cap = svc.jedec()
            sr1, sr2 = svc.status()
            board_mode = svc.mode()
            data = svc.read16(0x000000)
            stats = svc.stats()
    """

    def __init__(
        self,
        port: str | None = None,
        baud: int | None = None,
        timeout: float = 0.5,
        idle_gap: float = 0.002,
        *,
        target: BoardTarget | None = None,
        trace: bool = False,
        logger: LogCallback | None = None,
    ) -> None:
        self.port_name = port
        self.target = target or resolve_board_target(baud=baud)
        self.baud = self.target.baud if baud is None else baud
        self.timeout = timeout
        self.idle_gap = idle_gap
        self.trace = trace
        self.logger = logger
        self._serial = None
        self._erase_cmd: int = CMD_ERASE64
        self._info_cache: ServiceInfo | None = None
        self._sd_crc32_supported: bool | None = None
        self._sd_crc32_range_supported: bool | None = None
        self._seq: int = 0

    def __enter__(self) -> "FlashService":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        self.close()

    def open(self) -> None:
        """Open the serial connection (auto-discovers the port if needed)."""
        if self._serial is not None:
            return
        port = self.port_name or find_device_port(baud=self.baud, target=self.target)
        if not port:
            raise FlashServiceDiscoveryError(
                "IcePi Zero serial port was not found. If the board is not exposing UART, "
                "restore it with the repo-local admin wrapper first."
            )
        self.port_name = port
        serial = _load_pyserial()
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=self.baud,
                    timeout=0.0,
                    write_timeout=1.0,
                    inter_byte_timeout=0.0,
                    rtscts=False,
                    dsrdtr=False,
                    xonxoff=False,
                )
                break
            except Exception as exc:  # noqa: BLE001
                # pyserial folds the OS error (EACCES, EBUSY, ...) into its own
                # SerialException, so a bare `except PermissionError` never fires
                # here. Detect the permission case from the wrapped exception and
                # give a platform-specific, copy-pasteable fix.
                if _is_permission_error(exc):
                    raise FlashServiceDiscoveryError(
                        f"could not open port {port!r}: permission denied — "
                        f"{_serial_permission_hint(port)}"
                    ) from exc
                last_error = exc
                if attempt == 4:
                    raise FlashServiceDiscoveryError(
                        f"could not open port {port!r}: {exc}"
                    ) from exc
                time.sleep(0.05 * (attempt + 1))
        if self._serial is None and last_error is not None:
            raise FlashServiceDiscoveryError(
                f"could not open port {port!r}: {last_error}"
            ) from last_error
        assert self._serial is not None
        self._serial.dtr = False
        self._serial.rts = False
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        time.sleep(0.05)
        self._info_cache = None
        self._sd_crc32_supported = None
        self._sd_crc32_range_supported = None
        self._emit(f"opened {self.port_name} at {self.baud} baud")

    def close(self) -> None:
        """Close the serial connection and clear cached state."""
        if self._serial is not None:
            self._serial.close()
            self._serial = None
            self._info_cache = None
            self._sd_crc32_supported = None
            self._sd_crc32_range_supported = None
            self._emit("closed serial port")

    def mode(self) -> int:
        """Query the board mode (``MODE_APP`` / ``MODE_SERVICE``)."""
        frame = self._exchange(bytes([CMD_HELLO]), timeout=1.0, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_HELLO:
            raise FlashServiceProtocolError(f"unexpected HELLO response: {frame!r}")
        return frame[1]

    def ping(self) -> bool:
        """Send a PING and return ``True`` if the board acknowledges."""
        frame = self._exchange(bytes([CMD_PING]), timeout=1.0, min_len=2)
        return len(frame) >= 2 and frame[0] == CMD_PING and frame[1] == PING_REPLY

    def enter_service_mode(self) -> int:
        """Switch from app mode to service mode.  Returns the board mode."""
        frame = self._exchange(bytes([CMD_ENTER_SERVICE]), timeout=0.5, allow_empty=True)
        if frame:
            self._emit(f"service handoff ack {frame.hex(' ')}")
        time.sleep(0.15)
        mode = self.mode()
        if mode != MODE_SERVICE:
            raise FlashServiceProtocolError(f"service handoff failed, still in mode {mode}")
        return mode

    def exit_service_mode(self) -> int:
        """Return from service mode to app mode.  Returns the board mode."""
        frame = self._exchange(bytes([CMD_EXIT_SERVICE]), timeout=0.5, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_EXIT_SERVICE or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected EXIT_SERVICE response: {frame!r}")
        time.sleep(0.05)
        return self.mode()

    def uptime(self) -> int:
        """Query board uptime in seconds.  Works in both app and service mode."""
        frame = self._exchange(bytes([CMD_UPTIME]), timeout=1.0, min_len=5)
        if len(frame) < 5 or frame[0] != CMD_UPTIME:
            raise FlashServiceProtocolError(f"unexpected UPTIME response: {frame!r}")
        return (frame[1] << 24) | (frame[2] << 16) | (frame[3] << 8) | frame[4]

    def identity(self) -> dict[str, object]:
        """Query board identity.  Works in both app and service mode.

        Returns a dict with ``name`` and ``app_mode`` keys.
        """
        frame = self._exchange(bytes([CMD_IDENTITY]), timeout=1.0, min_len=6)
        if len(frame) < 6 or frame[0] != CMD_IDENTITY:
            raise FlashServiceProtocolError(f"unexpected IDENTITY response: {frame!r}")
        name = bytes(frame[1:5]).decode("ascii", errors="replace")
        return {
            "name": name,
            "app_mode": bool(frame[5]),
        }

    def assert_service(self) -> int:
        """Ensure the board is in service mode, entering it if needed.  Returns the board mode."""
        mode = self.mode()
        if is_startup_recovery_mode(mode):
            raise FlashServiceProtocolError(
                "board is in autonomous startup recovery; wait for completion or use `reload` to abort"
            )
        if mode == MODE_SERVICE:
            return mode
        mode = self.enter_service_mode()
        if mode != MODE_SERVICE:
            raise FlashServiceProtocolError(f"expected service mode, got mode {mode}")
        return mode

    def unlock(self) -> bool:
        """Send a write-unlock guard before destructive operations.

        The unlock key is the ASCII bytes ``RIME`` (``0x52 0x49 0x4D 0x45``).
        When the firmware supports unlock (advertised via capabilities), it
        gates ERASE64 and PROGRAM16 behind this handshake.  Firmware without
        unlock support returns an unknown-command error; the host ignores it
        and proceeds (backwards compatible).

        Returns ``True`` if the board acknowledged the unlock, ``False`` if
        the command was not recognized (old firmware).
        """
        try:
            frame = self._exchange(
                bytes([CMD_UNLOCK, 0x52, 0x49, 0x4D, 0x45]),
                timeout=0.5,
            )
            return len(frame) >= 2 and frame[0] == CMD_UNLOCK and frame[1] == PING_REPLY
        except (FlashServiceRemoteError, FlashServiceTimeout):
            return False

    def status(self) -> tuple[int, int]:
        """Read flash status registers.  Returns ``(sr1, sr2)``."""
        frame = self._exchange(bytes([CMD_STATUS]), timeout=1.0, min_len=3)
        if len(frame) < 3 or frame[0] != CMD_STATUS:
            raise FlashServiceProtocolError(f"unexpected STATUS response: {frame!r}")
        return frame[1], frame[2]

    def info(self) -> ServiceInfo:
        """Query service geometry and capabilities."""
        frame = self._exchange(bytes([CMD_INFO]), timeout=1.0, min_len=8)
        if len(frame) < 8 or frame[0] != CMD_INFO:
            raise FlashServiceProtocolError(f"unexpected INFO response: {frame!r}")
        info = ServiceInfo(
            caps0=frame[1],
            caps1=frame[2],
            max_program=frame[3],
            read_chunk=frame[4],
            erase_log2=frame[5],
            page_log2=frame[6],
            addr_bytes=frame[7],
        )
        self._info_cache = info
        return info

    def last_error(self) -> ServiceLastError:
        """Read the last error recorded by the service firmware."""
        frame = self._exchange(bytes([CMD_LAST_ERROR]), timeout=1.0, min_len=7)
        if len(frame) < 7 or frame[0] != CMD_LAST_ERROR:
            raise FlashServiceProtocolError(f"unexpected LAST_ERROR response: {frame!r}")
        return ServiceLastError(
            code=frame[1],
            command=frame[2],
            detail=frame[3],
            state=(frame[4] << 8) | frame[5],
            valid=bool(frame[6]),
        )

    def stats(self) -> ServiceStats:
        """Read cumulative service statistics (``command_count``, ``erase_count``, ``program_count``, ``error_count``)."""
        frame = self._exchange(bytes([CMD_STATS]), timeout=1.0, min_len=9)
        if len(frame) < 9 or frame[0] != CMD_STATS:
            raise FlashServiceProtocolError(f"unexpected STATS response: {frame!r}")
        return ServiceStats(
            command_count=(frame[1] << 8) | frame[2],
            erase_count=(frame[3] << 8) | frame[4],
            program_count=(frame[5] << 8) | frame[6],
            error_count=(frame[7] << 8) | frame[8],
        )

    def clear_last_error(self) -> None:
        """Clear the stored last-error state on the board."""
        frame = self._exchange(bytes([CMD_CLEAR_ERROR]), timeout=1.0, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_CLEAR_ERROR or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected CLEAR_ERROR response: {frame!r}")

    def debug(self) -> ServiceDebug:
        """Read detailed internal debug state from the service FSM."""
        frame = self._exchange(bytes([CMD_DEBUG]), timeout=1.0)
        if len(frame) < 10 or frame[0] != CMD_DEBUG:
            raise FlashServiceProtocolError(f"unexpected DEBUG response: {frame!r}")
        return ServiceDebug(
            state=frame[2],
            current_cmd=frame[3],
            spi_op=frame[4],
            addr_index=frame[5],
            data_index=frame[6],
            resp_len=frame[7],
            resp_pos=frame[8],
            flags=frame[9],
            auto_state=frame[10] if len(frame) > 10 else 0,
            auto_exit_reason=frame[11] if len(frame) > 11 else 0,
            auto_exit_detail=frame[12] if len(frame) > 12 else 0,
            auto_init_attempts=frame[13] if len(frame) > 13 else 0,
            auto_aux0=(
                frame[14] | (frame[15] << 8) | (frame[16] << 16) | (frame[17] << 24)
                if len(frame) > 17
                else 0
            ),
            auto_aux1=(
                frame[18] | (frame[19] << 8) | (frame[20] << 16) | (frame[21] << 24)
                if len(frame) > 21
                else 0
            ),
            auto_write_result=(
                frame[22] | (frame[23] << 8) | (frame[24] << 16) | (frame[25] << 24)
                if len(frame) > 25
                else 0
            ),
            auto_write_source_lba=(
                frame[26] | (frame[27] << 8) | (frame[28] << 16) | (frame[29] << 24)
                if len(frame) > 29
                else 0
            ),
        )

    def sd_info(self) -> SdInfo:
        """Query SD card presence, init state, and SD master debug fields.

        Note: bytes 6-9 are SD master FSM debug telemetry, not transaction
        counters. The host previously reported them as init/read counts;
        that was a contract drift bug (cure list item #13).
        """
        frame = self._exchange(bytes([CMD_SD_INFO]), timeout=2.0, min_len=10)
        if len(frame) < 10 or frame[0] != CMD_SD_INFO:
            raise FlashServiceProtocolError(f"unexpected SD_INFO response: {frame!r}")
        return SdInfo(
            flags=frame[1],
            last_error=frame[2],
            last_r1=frame[3],
            chunk_bytes=frame[4],
            chunks_per_block=frame[5],
            dbg_state=frame[6] & 0x1F,
            dbg_shift_in=frame[7],
            dbg_shift_busy=frame[8] & 0x01,
            svc_state=frame[9] & 0x1F,
        )

    def sd_init(self) -> SdInfo:
        """(Re-)initialize the SD card and return updated :class:`SdInfo`."""
        frame = self._exchange(bytes([CMD_SD_INIT]), timeout=8.0, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_SD_INIT or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected SD_INIT response: {frame!r}")
        return self.sd_info()

    def sd_read16(self, lba: int, chunk_index: int) -> bytes:
        """Read a 16-byte chunk from an SD block.  Returns ``bytes`` (16 bytes)."""
        if lba < 0:
            raise FlashServiceError("SD LBA must be non-negative")
        if not 0 <= chunk_index < 32:
            raise FlashServiceError("SD chunk index must be between 0 and 31")
        payload = bytes(
            [
                CMD_SD_READ16,
                (lba >> 24) & 0xFF,
                (lba >> 16) & 0xFF,
                (lba >> 8) & 0xFF,
                lba & 0xFF,
                chunk_index & 0x1F,
            ]
        )
        frame = self._exchange(payload, timeout=8.0, min_len=17)
        if len(frame) < 17 or frame[0] != CMD_SD_READ16:
            raise FlashServiceProtocolError(f"unexpected SD_READ16 response: {frame!r}")
        return bytes(frame[1:17])

    def _legacy_sd_crc32(self, lba: int) -> int:
        return binascii.crc32(self.sd_read(lba, offset=0, length=512)) & 0xFFFFFFFF

    def sd_crc32(self, lba: int) -> int:
        """Compute CRC32 of a single SD block on the board.  Returns ``int``."""
        if lba < 0:
            raise FlashServiceError("SD LBA must be non-negative")
        if self._sd_crc32_supported is None:
            self._sd_crc32_supported = True
        if not self._sd_crc32_supported:
            return self._legacy_sd_crc32(lba)
        payload = bytes(
            [
                CMD_SD_CRC32,
                (lba >> 24) & 0xFF,
                (lba >> 16) & 0xFF,
                (lba >> 8) & 0xFF,
                lba & 0xFF,
            ]
        )
        try:
            frame = self._exchange(payload, timeout=8.0, min_len=5)
        except FlashServiceRemoteError as exc:
            if exc.code == ERR_UNKNOWN_CMD:
                self._sd_crc32_supported = False
                return self._legacy_sd_crc32(lba)
            raise
        if len(frame) < 5 or frame[0] != CMD_SD_CRC32:
            raise FlashServiceProtocolError(f"unexpected SD_CRC32 response: {frame!r}")
        return (frame[1] << 24) | (frame[2] << 16) | (frame[3] << 8) | frame[4]

    def _legacy_sd_crc32_range(self, start_lba: int, block_count: int) -> int:
        crc = 0
        for offset in range(block_count):
            crc = binascii.crc32(self.sd_read(start_lba + offset, offset=0, length=512), crc)
        return crc & 0xFFFFFFFF

    def sd_crc32_range(self, start_lba: int, block_count: int) -> int:
        """Compute CRC32 over a contiguous range of SD blocks.  Returns ``int``."""
        if start_lba < 0:
            raise FlashServiceError("SD start LBA must be non-negative")
        if block_count <= 0:
            raise FlashServiceError("SD block count must be positive")
        if block_count == 1:
            return self.sd_crc32(start_lba)
        if self._sd_crc32_range_supported is None:
            self._sd_crc32_range_supported = True
        if not self._sd_crc32_range_supported:
            return self._legacy_sd_crc32_range(start_lba, block_count)
        if block_count > 0xFFFF:
            raise FlashServiceError("SD CRC range count must fit in 16 bits")
        payload = bytes(
            [
                CMD_SD_CRC32_RANGE,
                (start_lba >> 24) & 0xFF,
                (start_lba >> 16) & 0xFF,
                (start_lba >> 8) & 0xFF,
                start_lba & 0xFF,
                (block_count >> 8) & 0xFF,
                block_count & 0xFF,
            ]
        )
        try:
            frame = self._exchange(payload, timeout=max(8.0, block_count * 1.5), min_len=5)
        except FlashServiceRemoteError as exc:
            if exc.code == ERR_UNKNOWN_CMD:
                self._sd_crc32_range_supported = False
                return self._legacy_sd_crc32_range(start_lba, block_count)
            raise
        if len(frame) < 5 or frame[0] != CMD_SD_CRC32_RANGE:
            raise FlashServiceProtocolError(f"unexpected SD_CRC32_RANGE response: {frame!r}")
        return (frame[1] << 24) | (frame[2] << 16) | (frame[3] << 8) | frame[4]

    def sd_read(self, lba: int, *, offset: int = 0, length: int = 512) -> bytes:
        """Read up to 512 bytes from a single SD block.  Returns ``bytes``."""
        if lba < 0:
            raise FlashServiceError("SD LBA must be non-negative")
        if offset < 0 or length < 0:
            raise FlashServiceError("SD offset and length must be non-negative")
        if offset + length > 512:
            raise FlashServiceError("SD reads must stay within one 512-byte block")
        if length == 0:
            return b""
        start_chunk = offset // 16
        end_chunk = (offset + length + 15) // 16
        data = bytearray()
        for chunk_index in range(start_chunk, end_chunk):
            data.extend(self.sd_read16(lba, chunk_index))
        start = offset % 16
        return bytes(data[start : start + length])

    def sd_install(self, lba: int, *, timeout: float = 120.0, progress: "ProgressCallback | None" = None) -> None:
        """Install a RIME bundle from SD at *lba* into flash.

        Tries firmware-mediated CMD_SD_INSTALL first. Falls back to a
        host-mediated path (read SD → erase → program) if the firmware
        does not support the command.
        """
        if lba < 0:
            raise FlashServiceError("SD bundle LBA must be non-negative")
        try:
            frame = self._exchange(
                bytes([CMD_SD_INSTALL, (lba >> 24) & 0xFF, (lba >> 16) & 0xFF, (lba >> 8) & 0xFF, lba & 0xFF]),
                timeout=timeout, min_len=2,
            )
            if len(frame) >= 2 and frame[0] == CMD_SD_INSTALL and frame[1] == PING_REPLY:
                return
        except FlashServiceRemoteError as exc:
            if exc.code != ERR_UNKNOWN_CMD:
                raise
        self._sd_install_host(lba, progress=progress)

    def _sd_install_host(self, lba: int, *, progress: "ProgressCallback | None" = None) -> None:
        """Host-mediated SD bundle install: read SD → parse header → erase → program."""
        import struct
        header_data = self.sd_read(lba, offset=0, length=512)
        magic = header_data[:8]
        if magic != b"ICEPIB1\x00":
            raise FlashServiceError(f"SD block {lba} does not contain a valid RIME bundle (magic={magic!r})")
        fields = struct.unpack_from("<8sIIIIIIIII", header_data, 0)
        _magic, version, block_size, _manifest_bytes, image_offset, image_bytes, _image_padded, target_address, _reserved, _crc32 = fields
        if version != 1:
            raise FlashServiceError(f"unsupported bundle version {version}")
        if block_size == 0:
            raise FlashServiceError("bundle block size is zero")
        image_start_lba = lba + image_offset // block_size
        flash_addr = target_address
        chunk_size = 16
        erase_size = 65536
        total_chunks = (image_bytes + chunk_size - 1) // chunk_size
        sd_lba = image_start_lba
        sd_chunk = 0
        for idx in range(total_chunks):
            if flash_addr % erase_size == 0:
                if progress:
                    progress("erase", flash_addr // erase_size, (target_address + image_bytes) // erase_size + 1, f"0x{flash_addr:06X}")
                self.erase64(flash_addr)
            data = self.sd_read16(sd_lba, sd_chunk)
            self.program16(flash_addr, data)
            if progress:
                progress("write", idx, total_chunks, f"0x{flash_addr:06X}")
            flash_addr += chunk_size
            sd_chunk += 1
            if sd_chunk >= 32:
                sd_chunk = 0
                sd_lba += 1
        if progress:
            progress("write", total_chunks, total_chunks, None)

    def sd_write512(self, lba: int, data: bytes, *, timeout: float = 20.0) -> None:
        """Write exactly 512 bytes to an SD block at *lba*."""
        if lba < 0:
            raise FlashServiceError("SD write LBA must be non-negative")
        if len(data) != 512:
            raise FlashServiceError("SD block writes require exactly 512 bytes")
        frame = self._exchange(
            bytes(
                [
                    CMD_SD_WRITE512,
                    (lba >> 24) & 0xFF,
                    (lba >> 16) & 0xFF,
                    (lba >> 8) & 0xFF,
                    lba & 0xFF,
                ]
            )
            + data,
            timeout=timeout,
            min_len=2,
        )
        if len(frame) < 2 or frame[0] != CMD_SD_WRITE512 or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected SD_WRITE512 response: {frame!r}")

    def sdram_info(self) -> SdramInfo:
        """Query SDRAM controller status."""
        frame = self._exchange(bytes([CMD_SDRAM_INFO]), timeout=2.0, min_len=3)
        if len(frame) < 3 or frame[0] != CMD_SDRAM_INFO:
            raise FlashServiceProtocolError(f"unexpected SDRAM_INFO response: {frame!r}")
        flags = frame[1]
        return SdramInfo(init_done=bool(flags & 0x01), caps2=frame[2])

    def sdram_read16(self, word_address: int) -> bytes:
        """Read 16 bytes (8 words) from SDRAM starting at *word_address*."""
        _check_sdram_word_window("sdram_read16", word_address, 8)
        payload = bytes([
            CMD_SDRAM_READ16,
            (word_address >> 16) & 0xFF,
            (word_address >> 8) & 0xFF,
            word_address & 0xFF,
        ])
        frame = self._exchange(payload, timeout=2.0, min_len=17)
        if len(frame) < 17 or frame[0] != CMD_SDRAM_READ16:
            raise FlashServiceProtocolError(f"unexpected SDRAM_READ16 response: {frame!r}")
        return bytes(frame[1:17])

    def sdram_verify_local(self, word_address: int, expected: bytes, *, samples: int = 8) -> None:
        """Sample-read SDRAM and verify against *expected* data.

        Reads *samples* evenly-spaced 16-byte chunks from SDRAM and
        compares them to the corresponding portions of *expected*.
        Raises :class:`FlashServiceVerifyError` on mismatch.
        This is a pre-commit integrity check — call it after streaming
        to SDRAM and before committing to flash.
        """
        if len(expected) < 16:
            return
        total_chunks = len(expected) // 16
        step = max(1, total_chunks // samples)
        for i in range(0, total_chunks, step):
            offset = i * 16
            addr = word_address + offset // 2
            actual = self.sdram_read16(addr)
            if actual != expected[offset:offset + 16]:
                raise FlashServiceVerifyError(addr, expected[offset:offset + 16], actual)

    def sdram_write16(self, word_address: int, data: bytes) -> None:
        """Write 16 bytes (8 words) to SDRAM starting at *word_address*."""
        if len(data) != 16:
            raise FlashServiceError("SDRAM writes require exactly 16 bytes")
        _check_sdram_word_window("sdram_write16", word_address, 8)
        payload = bytes([
            CMD_SDRAM_WRITE16,
            (word_address >> 16) & 0xFF,
            (word_address >> 8) & 0xFF,
            word_address & 0xFF,
        ]) + data
        frame = self._exchange(payload, timeout=2.0, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_SDRAM_WRITE16 or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected SDRAM_WRITE16 response: {frame!r}")

    def sdram_write_stream(
        self, word_address: int, data: bytes, *, timeout: float = 120.0, spot_check: bool = False,
    ) -> None:
        """Stream bulk data to SDRAM in a single command.

        *data* length must be a multiple of 16.  The firmware receives the
        entire payload over UART and writes it to SDRAM in 16-byte chunks
        with no per-chunk ack.

        If *spot_check* is True, reads back the first and last 16-byte
        chunks from SDRAM after the stream and verifies they match the
        sent data.  This catches single-byte corruption from dropped UART
        bytes before the data is committed to flash.
        """
        if len(data) == 0 or len(data) % 16 != 0:
            raise FlashServiceError("stream data length must be a positive multiple of 16")
        if len(data) > 65535:
            raise FlashServiceError("stream data length must be <= 65535")
        _check_sdram_word_window("sdram_write_stream", word_address, len(data) // 2)
        self.open()
        assert self._serial is not None
        header = bytes([
            CMD_SDRAM_WRITE_STREAM,
            (word_address >> 16) & 0xFF,
            (word_address >> 8) & 0xFF,
            word_address & 0xFF,
            (len(data) >> 8) & 0xFF,
            len(data) & 0xFF,
        ])
        self._serial.reset_input_buffer()
        payload = header + data
        pos = 0
        while pos < len(payload):
            chunk = payload[pos : pos + 256]
            self._serial.write(chunk)
            pos += len(chunk)
        self._serial.flush()
        frame = self._read_frame(timeout=timeout, min_len=2)
        if not frame:
            raise FlashServiceTimeout(f"timeout waiting for {command_name(CMD_SDRAM_WRITE_STREAM)}")
        if len(frame) < 2 or frame[0] != CMD_SDRAM_WRITE_STREAM or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected SDRAM_WRITE_STREAM response: {frame!r}")
        if spot_check and len(data) >= 16:
            first_16 = self.sdram_read16(word_address)
            if first_16 != data[:16]:
                raise FlashServiceVerifyError(word_address, data[:16], first_16)
            if len(data) >= 32:
                last_word = word_address + (len(data) - 16) // 2
                last_16 = self.sdram_read16(last_word)
                if last_16 != data[-16:]:
                    raise FlashServiceVerifyError(last_word, data[-16:], last_16)

    def sdram_verify_flash(self, flash_address: int, byte_count: int, *, timeout: float = 120.0) -> None:
        """Verify SDRAM contents (from word 0) against flash on-board.

        Runs the read-compare loop entirely on-board at SPI speed.
        Raises :class:`FlashServiceRemoteError` if mismatch is detected.
        """
        if byte_count <= 0 or byte_count % 16 != 0:
            raise FlashServiceError("byte_count must be a positive multiple of 16")
        _check_flash_window("sdram_verify_flash", flash_address, byte_count)
        _check_sdram_word_window("sdram_verify_flash", 0, byte_count // 2)
        payload = bytes([
            CMD_SDRAM_VERIFY_FLASH,
            (flash_address >> 16) & 0xFF,
            (flash_address >> 8) & 0xFF,
            flash_address & 0xFF,
            (byte_count >> 16) & 0xFF,
            (byte_count >> 8) & 0xFF,
            byte_count & 0xFF,
        ])
        frame = self._exchange(payload, timeout=timeout, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_SDRAM_VERIFY_FLASH or frame[1] != PING_REPLY:
            if frame[0] == RESP_ERROR:
                raise FlashServiceProtocolError(f"on-board verify failed: {frame!r}")
            raise FlashServiceProtocolError(f"unexpected SDRAM_VERIFY_FLASH response: {frame!r}")

    def sdram_to_flash(self, flash_address: int, byte_count: int, *, timeout: float = 120.0) -> None:
        """Commit SDRAM contents (starting at word 0) to flash.

        Runs the erase→program loop entirely on-board at SPI speed.
        *flash_address* is the destination byte address in flash.
        *byte_count* must be a multiple of 16.
        """
        if byte_count <= 0 or byte_count % 16 != 0:
            raise FlashServiceError("byte_count must be a positive multiple of 16")
        _check_flash_window("sdram_to_flash", flash_address, byte_count)
        _check_sdram_word_window("sdram_to_flash", 0, byte_count // 2)
        payload = bytes([
            CMD_SDRAM_TO_FLASH,
            (flash_address >> 16) & 0xFF,
            (flash_address >> 8) & 0xFF,
            flash_address & 0xFF,
            (byte_count >> 16) & 0xFF,
            (byte_count >> 8) & 0xFF,
            byte_count & 0xFF,
        ])
        frame = self._exchange(payload, timeout=timeout, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_SDRAM_TO_FLASH or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected SDRAM_TO_FLASH response: {frame!r}")

    def jedec(self) -> tuple[int, int, int]:
        """Read flash JEDEC ID.  Returns ``(manufacturer, device_type, capacity)``."""
        frame = self._exchange(bytes([CMD_JEDEC]), timeout=2.0, min_len=4)
        if len(frame) < 4 or frame[0] != CMD_JEDEC:
            raise FlashServiceProtocolError(f"unexpected JEDEC response: {frame!r}")
        return frame[1], frame[2], frame[3]

    def read16(self, address: int) -> bytes:
        """Read one chunk (typically 16 bytes) from flash.  Returns ``bytes``."""
        command = CMD_READ16
        chunk_size = (self._info_cache.read_chunk if self._info_cache is not None else 16) or 16
        _check_flash_window("read16", address, chunk_size)
        payload = bytes(
            [command, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF]
        )
        expected_len = 1 + chunk_size
        frame = self._exchange(payload, timeout=1.0, min_len=expected_len)
        if len(frame) < expected_len or frame[0] != command:
            raise FlashServiceProtocolError(f"unexpected READ16 response: {frame!r}")
        return bytes(frame[1:expected_len])

    def read(self, address: int, length: int) -> bytes:
        """Read *length* bytes from flash starting at *address*.  Returns ``bytes``."""
        _check_flash_window("read", address, length)
        if length == 0:
            return b""
        if self._info_cache is None:
            self.info()
        data = bytearray()
        offset = 0
        while offset < length:
            chunk = self.read16(address + offset)
            take = min(len(chunk), length - offset)
            data.extend(chunk[:take])
            offset += take
        return bytes(data)

    def software_reset(self) -> bool:
        """Trigger a firmware-initiated CPU reset.

        Sends CMD_SW_RESET and waits for the ACK before the board resets.
        Returns ``True`` if acknowledged, ``False`` on timeout (board may
        have reset before the ACK was received).
        """
        try:
            frame = self._exchange(bytes([CMD_SW_RESET]), timeout=2.0, min_len=2)
            return len(frame) >= 2 and frame[0] == CMD_SW_RESET and frame[1] == PING_REPLY
        except FlashServiceTimeout:
            return False

    def set_watchdog(self, seconds: int) -> bool:
        """Set the hardware watchdog timeout in seconds (0 = disable).

        Requires firmware support for CMD_SET_WATCHDOG (0x87).
        Returns ``True`` if acknowledged, ``False`` if unsupported.
        """
        clk_hz = 25000000
        cycles = seconds * clk_hz if seconds > 0 else 0
        payload = bytes([
            CMD_SET_WATCHDOG,
            (cycles >> 24) & 0xFF,
            (cycles >> 16) & 0xFF,
            (cycles >> 8) & 0xFF,
            cycles & 0xFF,
        ])
        try:
            frame = self._exchange(payload, timeout=1.0, min_len=2)
            return len(frame) >= 2 and frame[0] == CMD_SET_WATCHDOG and frame[1] == PING_REPLY
        except (FlashServiceRemoteError, FlashServiceTimeout):
            return False

    def verify_bytes(
        self,
        address: int,
        expected: bytes,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        """Verify that flash contents at *address* match *expected*.

        Raises :class:`FlashServiceVerifyError` on the first mismatch.
        """
        if address < 0:
            raise FlashServiceError("verify address must be non-negative")
        if not expected:
            return
        if self._info_cache is None:
            self.info()
        read_size = (self._info_cache.read_chunk if self._info_cache is not None else 16) or 16
        chunks = (len(expected) + read_size - 1) // read_size
        for index in range(chunks):
            data_offset = index * read_size
            chunk_address = address + data_offset
            wanted = expected[data_offset : data_offset + read_size]
            if progress:
                progress("verify", index, chunks, f"0x{chunk_address:06X}")
            actual = self.read(chunk_address, len(wanted))
            if actual != wanted:
                raise FlashServiceVerifyError(chunk_address, wanted, actual)
        if progress:
            progress("verify", chunks, chunks, None)

    def erase64(self, address: int) -> None:
        """Erase a 64 KiB sector at *address*.  Inline 'RIME' key prefix."""
        _check_flash_window("erase64", address, 0x10000)
        payload = bytes(
            [self._erase_cmd, 0x52, 0x49, 0x4D, 0x45,
             (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF]
        )
        frame = self._exchange(payload, timeout=6.0, min_len=2)
        if len(frame) < 2 or frame[0] != self._erase_cmd or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected ERASE64 response: {frame!r}")

    def program16(self, address: int, chunk: bytes) -> None:
        """Program exactly 16 bytes into flash at *address*.  Inline 'RIME' key prefix."""
        if len(chunk) != 16:
            raise ValueError("program16 expects exactly 16 bytes")
        _check_flash_window("program16", address, 16)
        payload = bytes(
            [CMD_PROGRAM16, 0x52, 0x49, 0x4D, 0x45,
             (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF]
        ) + chunk
        frame = self._exchange(payload, timeout=2.0, min_len=2)
        if len(frame) < 2 or frame[0] != CMD_PROGRAM16 or frame[1] != PING_REPLY:
            raise FlashServiceProtocolError(f"unexpected PROGRAM16 response: {frame!r}")

    def probe(
        self,
        auto_enter: bool = False,
        *,
        include_flash: bool = False,
        include_debug: bool = False,
        include_sd: bool = True,
    ) -> ServiceSnapshot:
        """Probe the board and collect a composite snapshot of its state."""
        mode = self.mode()
        if is_startup_recovery_mode(mode):
            return ServiceSnapshot(
                port=self.port_name or "",
                mode="startup",
            )
        if is_startup_failsafe_mode(mode):
            return ServiceSnapshot(
                port=self.port_name or "",
                mode="failsafe",
            )
        if mode != MODE_SERVICE and auto_enter:
            mode = self.enter_service_mode()
        if mode == MODE_SERVICE:
            snapshot = ServiceSnapshot(
                port=self.port_name or "",
                mode="service",
            )
            try:
                snapshot.info = self.info()
            except FlashServiceError:
                pass
            try:
                snapshot.last_error = self.last_error()
            except FlashServiceError:
                pass
            try:
                snapshot.stats = self.stats()
            except FlashServiceError:
                pass
            if include_debug:
                try:
                    snapshot.debug = self.debug()
                except FlashServiceError:
                    pass
            if include_flash:
                try:
                    snapshot.status = self.status()
                except FlashServiceError:
                    pass
                try:
                    snapshot.jedec = self.jedec()
                except FlashServiceError:
                    pass
            if include_sd and (snapshot.info is None or snapshot.info.caps1 & CAPS1_SD_INFO):
                try:
                    snapshot.sd_info = self.sd_info()
                except FlashServiceError:
                    pass
            return snapshot
        return ServiceSnapshot(
            port=self.port_name or "",
            mode="app",
        )

    def upload_bitstream(
        self,
        bitstream_path: str | Path,
        *,
        base_address: int = 0,
        max_bytes: int | None = None,
        verify: bool = True,
        progress: ProgressCallback | None = None,
        retries: int = 1,
        wipe_slot: bool = False,
    ) -> "UploadResult":
        """Erase, program, and optionally verify a bitstream via the resident service.

        Routes through SDRAM staging (one UNLOCK + one on-board commit loop)
        with chunked SDRAM fallback for row-aliased boards. The old per-chunk
        direct path — which issued ~12,700 UNLOCK round-trips for a 200 KB
        install (~407 s) — has been removed. If SDRAM is unavailable the
        install fails loudly rather than falling back to the slow path.

        Pass *wipe_slot=True* (typical for bootable slots) to erase every
        sector in [base_address, base_address + max_bytes) before commit,
        eliminating old-bitstream remnants past the new image.

        The *retries* parameter is accepted for backwards compatibility but
        unused; the staged path verifies on-board via SDRAM_VERIFY_FLASH.
        """
        del retries  # staged path verifies on-board
        try:
            return self.upload_bitstream_staged(
                bitstream_path,
                base_address=base_address,
                max_bytes=max_bytes,
                verify=verify,
                progress=progress,
                wipe_slot=wipe_slot,
            )
        except FlashServiceError as staged_exc:
            self._emit(f"staged upload failed ({staged_exc}); trying chunked SDRAM path")
            try:
                self.flush_raw(b"\xFF" * 4096)
                import time as _time
                _time.sleep(0.3)
                self.close()
                _time.sleep(0.3)
                self.open()
                self.assert_service()
            except FlashServiceError:
                raise staged_exc
            return self.upload_bitstream_chunked(
                bitstream_path,
                base_address=base_address,
                max_bytes=max_bytes,
                verify=verify,
                progress=progress,
                wipe_slot=wipe_slot,
            )

    def upload_bitstream_staged(
        self,
        bitstream_path: str | Path,
        *,
        base_address: int = 0,
        max_bytes: int | None = None,
        verify: bool = True,
        progress: "ProgressCallback | None" = None,
        wipe_slot: bool = False,
    ) -> "UploadResult":
        """Upload via SDRAM staging: stream to SDRAM, then on-board commit to flash.

        Significantly faster than the legacy direct path because the
        erase/program phase runs at SPI speed with no UART round-trips.

        When *wipe_slot* is True (caller passes True for bootable slots),
        every 64 KiB sector in [base_address, base_address + max_bytes)
        is erased before commit, eliminating any old-image remnants past
        the new bitstream's padded end. This is the recommended default
        when installing into the boot slot.
        """
        self.assert_service()
        bitstream = strip_bitstream_header(Path(bitstream_path).read_bytes())
        if not bitstream:
            raise FlashServiceError("bitstream is empty")
        info = self.info()
        chunk_size = info.max_program
        erase_size = info.erase_size
        padded_len = ((len(bitstream) + chunk_size - 1) // chunk_size) * chunk_size
        image = bitstream + (b"\xFF" * (padded_len - len(bitstream)))
        if base_address < 0:
            raise FlashServiceError("base address must be non-negative")
        if base_address % erase_size != 0:
            raise FlashServiceError(
                f"base address 0x{base_address:06X} is not aligned to erase size {erase_size}"
            )
        if max_bytes is not None and padded_len > max_bytes:
            raise FlashServiceError(
                f"image needs {padded_len} bytes but target reserves only {max_bytes} bytes"
            )

        # Full-slot wipe: erase every sector past the bitstream's padded end
        # so old-bitstream remnants never leak into a fresh install.
        if wipe_slot and max_bytes is not None and max_bytes > padded_len:
            wipe_start = base_address + ((padded_len + erase_size - 1) // erase_size) * erase_size
            wipe_end = base_address + max_bytes
            wipe_addr = wipe_start
            wipe_total = max(0, (wipe_end - wipe_start + erase_size - 1) // erase_size)
            wipe_idx = 0
            while wipe_addr < wipe_end:
                if progress:
                    progress("wipe", wipe_idx, wipe_total, f"0x{wipe_addr:06X}")
                self.erase64(wipe_addr)
                wipe_addr += erase_size
                wipe_idx += 1
            if progress and wipe_total:
                progress("wipe", wipe_total, wipe_total, None)

        # Phase 1: stream the entire padded image into SDRAM in 4 KB blocks.
        # Each SDRAM_WRITE_STREAM command transfers one block over UART into
        # sequential SDRAM word addresses. Word address = byte address / 2
        # because SDRAM is 16-bit.
        stream_block = 4096
        sdram_word = 0
        total_blocks = (padded_len + stream_block - 1) // stream_block
        for block_idx in range(total_blocks):
            offset = block_idx * stream_block
            end = min(offset + stream_block, padded_len)
            chunk = image[offset:end]
            if len(chunk) % 16 != 0:
                chunk = chunk + b"\xFF" * (16 - len(chunk) % 16)
            if progress:
                progress("upload", block_idx, total_blocks, f"{len(chunk)} bytes")
            self.sdram_write_stream(sdram_word, chunk)
            sdram_word += len(chunk) // 2  # advance by words, not bytes
        if progress:
            progress("upload", total_blocks, total_blocks, None)

        # Phase 2: commit SDRAM contents to flash at SPI speed.
        # SDRAM_TO_FLASH runs the erase→program loop entirely on-board
        # with no UART round-trips per chunk. Erase is triggered at each
        # 64 KiB sector boundary automatically by the firmware FSM.
        if progress:
            progress("commit", 0, 1, f"{padded_len} bytes to flash 0x{base_address:06X}")
        commit_timeout = max(30.0, padded_len / 500.0)
        self.sdram_to_flash(base_address, padded_len, timeout=commit_timeout)
        if progress:
            progress("commit", 1, 1, None)

        # Phase 3: on-board verify — SDRAM_VERIFY_FLASH compares SDRAM
        # word 0 against flash at the target address, 16 bytes at a time,
        # entirely on-board. No UART traffic during verify.
        if verify:
            if progress:
                progress("verify", 0, 1, f"{padded_len} bytes on-board")
            verify_timeout = max(30.0, padded_len / 1000.0)
            self.sdram_verify_flash(base_address, padded_len, timeout=verify_timeout)
            if progress:
                progress("verify", 1, 1, None)

        return UploadResult(
            base_address=base_address,
            bytes=len(bitstream),
            padded_bytes=padded_len,
            erase_size=erase_size,
            chunk_size=chunk_size,
        )

    def upload_bitstream_chunked(
        self,
        bitstream_path: str | Path,
        *,
        base_address: int = 0,
        max_bytes: int | None = None,
        verify: bool = True,
        progress: "ProgressCallback | None" = None,
        sdram_chunk: int = 1024,
        wipe_slot: bool = False,
    ) -> "UploadResult":
        """Upload via repeated SDRAM stream+commit cycles.

        Uses only *sdram_chunk* bytes of SDRAM per iteration (default 1024,
        which fits in a single row of one bank even with row aliasing).
        Each iteration streams a chunk to SDRAM word 0, then commits it
        to flash at the correct offset.  Erase is performed once per
        64 KiB sector boundary.

        When *wipe_slot* is True, all sectors in [base_address,
        base_address + max_bytes) past the bitstream's padded end are
        erased after the main commit so old-image remnants do not survive
        a fresh install.
        """
        self.assert_service()
        bitstream = strip_bitstream_header(Path(bitstream_path).read_bytes())
        if not bitstream:
            raise FlashServiceError("bitstream is empty")
        info = self.info()
        chunk_size = info.max_program
        erase_size = info.erase_size
        padded_len = ((len(bitstream) + chunk_size - 1) // chunk_size) * chunk_size
        image = bitstream + (b"\xFF" * (padded_len - len(bitstream)))
        if base_address < 0:
            raise FlashServiceError("base address must be non-negative")
        if base_address % erase_size != 0:
            raise FlashServiceError(
                f"base address 0x{base_address:06X} is not aligned to erase size {erase_size}"
            )
        if max_bytes is not None and padded_len > max_bytes:
            raise FlashServiceError(
                f"image needs {padded_len} bytes but target reserves only {max_bytes} bytes"
            )
        if sdram_chunk % 16 != 0 or sdram_chunk <= 0:
            raise FlashServiceError("sdram_chunk must be a positive multiple of 16")

        total_chunks = (padded_len + sdram_chunk - 1) // sdram_chunk

        for idx in range(total_chunks):
            offset = idx * sdram_chunk
            flash_addr = base_address + offset
            end = min(offset + sdram_chunk, padded_len)
            block = image[offset:end]
            if len(block) % 16 != 0:
                block = block + b"\xFF" * (16 - len(block) % 16)

            if flash_addr % erase_size == 0:
                if progress:
                    progress("erase", flash_addr // erase_size, (base_address + padded_len + erase_size - 1) // erase_size, f"0x{flash_addr:06X}")
                self.erase64(flash_addr)

            if progress:
                progress("write", idx, total_chunks, f"0x{flash_addr:06X}")
            self.sdram_write_stream(0, block, timeout=10.0)
            self.sdram_to_flash(flash_addr, len(block), timeout=30.0)

        if progress:
            progress("write", total_chunks, total_chunks, None)

        # Wipe trailing sectors past the bitstream end if requested
        if wipe_slot and max_bytes is not None and max_bytes > padded_len:
            wipe_start = base_address + ((padded_len + erase_size - 1) // erase_size) * erase_size
            wipe_end = base_address + max_bytes
            wipe_addr = wipe_start
            while wipe_addr < wipe_end:
                if progress:
                    progress("wipe", (wipe_addr - wipe_start) // erase_size,
                             (wipe_end - wipe_start) // erase_size, f"0x{wipe_addr:06X}")
                self.erase64(wipe_addr)
                wipe_addr += erase_size

        if verify:
            for idx in range(total_chunks):
                offset = idx * sdram_chunk
                flash_addr = base_address + offset
                end = min(offset + sdram_chunk, padded_len)
                block = image[offset:end]
                if len(block) % 16 != 0:
                    block = block + b"\xFF" * (16 - len(block) % 16)
                if progress:
                    progress("verify", idx, total_chunks, f"0x{flash_addr:06X}")
                self.sdram_write_stream(0, block, timeout=10.0)
                self.sdram_verify_flash(flash_addr, len(block), timeout=30.0)
            if progress:
                progress("verify", total_chunks, total_chunks, None)

        return UploadResult(
            base_address=base_address,
            bytes=len(bitstream),
            padded_bytes=padded_len,
            erase_size=erase_size,
            chunk_size=chunk_size,
        )

    def flush_raw(self, data: bytes) -> None:
        """Write raw bytes to the serial port, bypassing protocol framing.

        Used by recovery paths that need to satisfy a stuck firmware FSM
        (e.g. padding bytes to complete an interrupted SDRAM stream).
        """
        if self._serial is not None:
            self._serial.write(data)
            self._serial.flush()

    def _emit(self, message: str) -> None:
        if not self.trace and self.logger is None:
            return
        if self.logger is not None:
            self.logger(message)
        elif self.trace:
            print(message)

    def raw_exchange(
        self,
        payload: bytes,
        *,
        timeout: float,
        allow_empty: bool = False,
        min_len: int | None = None,
    ) -> bytes:
        """Send a raw payload and return the raw response frame.

        This is the public entry for callers that need to drive the protocol
        below the typed-command layer (e.g. the shell `raw` builtin, or the
        chain regression's adversarial probes). The internal `_exchange`
        method delegates here so all framing/CRC/error-frame logic lives in
        one place.
        """
        return self._exchange(
            payload,
            timeout=timeout,
            allow_empty=allow_empty,
            min_len=min_len,
        )

    def _exchange(
        self,
        payload: bytes,
        *,
        timeout: float,
        allow_empty: bool = False,
        min_len: int | None = None,
    ) -> bytes:
        """Send a command payload and read the response frame.

        Reads the length-prefixed response (via _read_frame, which validates
        the CRC-8 and returns the payload), detects error frames (payload[0]
        == 0xFF), and raises typed exceptions with decoded details. All
        protocol round-trips go through this method. Requests are raw command
        bytes — only responses are framed.
        """
        self.open()
        assert self._serial is not None
        seq = self._seq
        self._seq = (self._seq + 1) & 0xFF
        self._emit(f"[{seq:3d}] tx {command_name(payload[0])}: {payload.hex(' ')}")
        self._serial.reset_input_buffer()
        self._serial.write(payload)
        self._serial.flush()
        frame = self._read_frame(timeout=timeout, min_len=min_len)
        if not frame and allow_empty:
            self._emit(f"[{seq:3d}] rx {command_name(payload[0])}: <empty allowed>")
            return b""
        if not frame:
            raise FlashServiceTimeout(f"timeout waiting for {command_name(payload[0])}")
        self._emit(f"[{seq:3d}] rx {command_name(payload[0])}: {frame.hex(' ')}")
        if frame[0] == RESP_ERROR:
            if len(frame) >= 8:
                raise FlashServiceRemoteError(
                    code=frame[1],
                    state=(frame[2] << 8) | frame[3],
                    command=frame[4],
                    detail=frame[5],
                    flags=frame[6],
                    op=frame[7],
                    seq=seq,
                )
            if len(frame) >= 5:
                raise FlashServiceRemoteError(
                    code=frame[1],
                    state=frame[2],
                    command=frame[3],
                    detail=frame[4],
                    seq=seq,
                )
            raise FlashServiceProtocolError(f"short error frame (seq={seq}): {frame!r}")
        return frame

    def _try_exchange(self, payload: bytes, *, timeout: float) -> bytes | None:
        try:
            return self._exchange(payload, timeout=timeout)
        except FlashServiceTimeout:
            return None
        except FlashServiceRemoteError:
            return None

    def _read_frame(self, *, timeout: float, min_len: int | None = None) -> bytes:
        """Read one length-prefixed response frame and return its payload.

        Reads ``[type, len_lo, len_hi, payload, crc8]``, validates the CRC-8,
        and returns the payload bytes (empty on timeout). *min_len* is accepted
        for call-site compatibility but unused — the length is explicit on the
        wire.
        """
        assert self._serial is not None
        result = _read_length_prefixed(self._serial, timeout=timeout)
        if result is None:
            return b""
        return result[1]
