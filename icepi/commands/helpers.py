"""Shared helpers used across RIME command implementations."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Never

from icepi.build import resolve_bitstream_target  # noqa: F401 — re-export
from icepi.flash_service import (
    DeviceSnapshot,
    FlashService,
    FlashServiceProtocolError,
    ServiceSnapshot,
    SdInfo,
    describe_state_code,
    probe_device,
    resolve_board_target_from_args,
)
from icepi.layout import load_layout, plan_image
from icepi.models import LayoutConfig, ResolvedBitstream
from icepi.tools import admin_script_command, find_admin_script, make_progress_renderer  # noqa: F401

__all__ = [
    "CommandParseError",
    "ShellInputError",
    "FriendlyArgumentParser",
    "load_layout_from_args",
    "build_plan_for_args",
    "make_service",
    "explain_snapshot",
    "explain_device",
    "print_usb_notes_for_args",
    "snapshot_mode_label",
    "render_sd_info_lines",
    "capture_snapshot",
    "ensure_service",
    "print_service_mode_note",
    "validate_flash_window",
    "validate_sd_window",
    "render_hexdump",
    "print_plan_header",
    "resolved_as_dict",
    "run_reload",
    "set_session_service",
    "clear_session_service",
]


# When the interactive shell is running it pins its one open FlashService here;
# make_service then hands every command that connection (wrapped so a handler's
# `with make_service(...)` block never closes it) instead of dialing a fresh
# one. That is what makes the shell a single live session rather than a
# per-command re-dispatch of the one-shot CLI.
_SESSION_SERVICE: "FlashService | None" = None


class _PinnedService:
    def __init__(self, svc: "FlashService") -> None:
        object.__setattr__(self, "_svc", svc)

    def __enter__(self) -> "_PinnedService":
        object.__getattribute__(self, "_svc").open()
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def open(self) -> None:
        object.__getattribute__(self, "_svc").open()

    def close(self) -> None:
        pass

    def __getattr__(self, name: str) -> object:
        return getattr(object.__getattribute__(self, "_svc"), name)


def set_session_service(svc: "FlashService | None") -> None:
    global _SESSION_SERVICE
    _SESSION_SERVICE = svc


def clear_session_service() -> None:
    global _SESSION_SERVICE
    _SESSION_SERVICE = None


class CommandParseError(ValueError):
    def __init__(self, message: str, usage: str | None = None, *, status: int = 2) -> None:
        super().__init__(message)
        self.usage = usage.strip() if usage else None
        self.status = status


class ShellInputError(ValueError):
    pass


class FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:  # type: ignore[override]
        raise CommandParseError(message, self.format_usage())


def load_layout_from_args(args: argparse.Namespace) -> LayoutConfig:
    return load_layout(args.layout)


def build_plan_for_args(  # type: ignore[no-untyped-def]
    bitstream: Path,
    args: argparse.Namespace,
    *,
    chunk_size: int,
    erase_size: int,
):
    layout = load_layout_from_args(args)
    plan = plan_image(
        bitstream,
        layout=layout,
        slot_name=getattr(args, "slot", None),
        address=getattr(args, "address", None),
        reserved_bytes=getattr(args, "reserved_bytes", None),
        chunk_size=chunk_size,
        erase_size=erase_size,
    )
    return layout, plan


def make_service(args: argparse.Namespace) -> FlashService:
    if _SESSION_SERVICE is not None:
        return _PinnedService(_SESSION_SERVICE)  # type: ignore[return-value]

    def logger(message: str) -> None:
        print(f"[trace] {message}")

    target = resolve_board_target_from_args(args)
    baud = args.baud if args.baud is not None else target.baud
    return FlashService(
        port=args.port,
        baud=baud,
        target=target,
        trace=args.trace,
        logger=logger if args.trace else None,
    )


def explain_snapshot(snapshot: ServiceSnapshot) -> list[str]:
    lines = [f"Port: {snapshot.port}", f"Mode: {snapshot.mode}"]
    if snapshot.mode == "startup":
        lines.append("Recovery: autonomous SD install is active.")
    elif snapshot.mode == "failsafe":
        lines.append("Recovery: startup failsafe tripped; app mode was restored.")
    if snapshot.jedec is not None:
        lines.append("Flash: " + " ".join(f"0x{value:02X}" for value in snapshot.jedec))
    if snapshot.status is not None:
        lines.append(
            f"Status: sr1=0x{snapshot.status[0]:02X} sr2=0x{snapshot.status[1]:02X}"
        )
    if snapshot.info is not None:
        lines.append(
            "Geometry: "
            f"max_program={snapshot.info.max_program}B "
            f"read_chunk={snapshot.info.read_chunk}B "
            f"erase={snapshot.info.erase_size // 1024}KiB "
            f"page={snapshot.info.page_size}B "
            f"addr_bytes={snapshot.info.addr_bytes}"
        )
        lines.append("Caps: " + ", ".join(snapshot.info.caps))
    if snapshot.last_error is not None:
        if snapshot.last_error.valid:
            lines.append(
                "Last error: "
                f"{snapshot.last_error.name} on {snapshot.last_error.command:#04x} "
                f"(detail={snapshot.last_error.detail_name}, "
                f"state={describe_state_code(snapshot.last_error.state)})"
            )
        else:
            lines.append("Last error: clear")
    if snapshot.stats is not None:
        lines.append(
            "Stats: "
            f"cmds={snapshot.stats.command_count} "
            f"erase={snapshot.stats.erase_count} "
            f"program={snapshot.stats.program_count} "
            f"errors={snapshot.stats.error_count}"
        )
    if snapshot.sd_info is not None:
        media = "present" if snapshot.sd_info.card_present else "not-present"
        init = "ready" if snapshot.sd_info.initialized else "cold"
        card_type = "sdhc" if snapshot.sd_info.high_capacity else "unsupported"
        lines.append(
            "SD: "
            f"{media} "
            f"{init} "
            f"{card_type} "
            f"r1=0x{snapshot.sd_info.last_r1:02X} "
            f"last_error={snapshot.sd_info.last_error_name} "
            f"dbg_state={snapshot.sd_info.dbg_state} "
            f"shift_in=0x{snapshot.sd_info.dbg_shift_in:02X}"
        )
    if snapshot.debug is not None:
        lines.append(
            "Debug: "
            f"state={snapshot.debug.state_name} "
            f"cmd={snapshot.debug.current_cmd_name} "
            f"spi={snapshot.debug.spi_op_name} "
            f"addr_index={snapshot.debug.addr_index} "
            f"data_index={snapshot.debug.data_index} "
            f"resp={snapshot.debug.resp_pos}/{snapshot.debug.resp_len} "
            f"flags={','.join(snapshot.debug.flag_names)} "
            f"auto={snapshot.debug.auto_state_name} "
            f"exit={snapshot.debug.auto_exit_reason_name} "
            f"progress={snapshot.debug.auto_progress_text}"
        )
    return lines


def explain_device(device: DeviceSnapshot) -> list[str]:
    lines = [
        f"Device present: {'yes' if device.present else 'no'}",
        f"USB mode: {device.mode}",
    ]
    if device.com_port:
        lines.append(f"Serial port: {device.com_port}")
    if device.driver:
        lines.append(f"Driver: {device.driver}")
    if device.friendly_name:
        lines.append(f"Device: {device.friendly_name}")
    if device.service:
        lines.append(f"Service: {device.service}")
    if device.instance_id:
        lines.append(f"Instance: {device.instance_id}")
    for note in device.notes:
        lines.append(f"Note: {note}")
    return lines


def print_usb_notes_for_args(args: argparse.Namespace) -> dict[str, object]:
    target = resolve_board_target_from_args(args)
    usb = probe_device(target=target, baud=target.baud)
    for line in explain_device(usb):
        print(line)
    return asdict(usb)


def snapshot_mode_label(snapshot: ServiceSnapshot) -> str:
    if snapshot.mode == "startup":
        return "startup-recovery"
    if snapshot.mode == "failsafe":
        return "startup-failsafe"
    return snapshot.mode


def render_sd_info_lines(sd_info: SdInfo) -> list[str]:
    if not sd_info.card_present and sd_info.initialized:
        present_text = "no (detect pin absent, but card responds)"
    elif sd_info.card_present:
        present_text = "yes"
    else:
        present_text = "no"
    return [
        f"Present: {present_text}",
        f"Initialized: {'yes' if sd_info.initialized else 'no'}",
        f"Capacity mode: {'SDHC/SDXC' if sd_info.high_capacity else 'unsupported (SDSC)'}",
        f"Last R1: 0x{sd_info.last_r1:02X}",
        f"Last error: {sd_info.last_error_name} (0x{sd_info.last_error:02X})",
        f"Chunk bytes: {sd_info.chunk_bytes}",
        f"Chunks per block: {sd_info.chunks_per_block}",
        f"SD master FSM state: {sd_info.dbg_state}",
        f"SD master shift-in: 0x{sd_info.dbg_shift_in:02X}",
        f"SD master shift-busy: {sd_info.dbg_shift_busy}",
        f"Service FSM state at read: {sd_info.svc_state}",
    ]


def capture_snapshot(service: FlashService, *, auto_enter: bool) -> tuple[ServiceSnapshot, bool]:
    snapshot = service.probe(auto_enter=False)
    if auto_enter and snapshot.mode == "app":
        snapshot = service.probe(auto_enter=True)
        return snapshot, True
    return snapshot, False


def ensure_service(service: FlashService) -> tuple[ServiceSnapshot, bool]:
    snapshot = service.probe(auto_enter=False)
    if snapshot.mode == "service":
        return snapshot, False
    if snapshot.mode == "startup":
        raise FlashServiceProtocolError(
            "board is in autonomous startup recovery; wait for completion or use `reload` to abort"
        )
    service.assert_service()
    return service.probe(auto_enter=False), True


def print_service_mode_note(entered_service: bool) -> None:
    if entered_service:
        print("Note: board is now in service mode. Use `reload` to return to the resident app.")


def validate_flash_window(address: int, length: int, *, layout: LayoutConfig) -> None:
    if address < 0:
        raise ValueError("flash address must be non-negative")
    if length < 0:
        raise ValueError("flash length must be non-negative")
    if address + length > layout.flash_size:
        raise ValueError(
            f"requested range 0x{address:06X}-0x{address + length - 1:06X} exceeds flash size 0x{layout.flash_size:06X}"
        )


def validate_sd_window(offset: int, length: int) -> None:
    if offset < 0:
        raise ValueError("SD offset must be non-negative")
    if length < 0:
        raise ValueError("SD length must be non-negative")
    if offset + length > 512:
        raise ValueError("SD reads must stay within one 512-byte block")


def render_hexdump(data: bytes, *, base_address: int, width: int = 16) -> list[str]:
    if width <= 0:
        raise ValueError("hex width must be positive")
    lines: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset: offset + width]
        hex_bytes = " ".join(f"{byte:02X}" for byte in chunk).ljust((width * 3) - 1)
        ascii_text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{base_address + offset:06X}: {hex_bytes}  |{ascii_text}|")
    return lines


def print_plan_header(resolved: ResolvedBitstream) -> None:
    if resolved.project:
        state = "built" if resolved.built else "existing"
        print(f"Target project: {resolved.project} ({state} bitstream)")


def resolved_as_dict(resolved: ResolvedBitstream) -> dict[str, object]:
    return {
        "spec": resolved.spec,
        "bitstream": str(resolved.bitstream),
        "project": resolved.project,
        "built": resolved.built,
    }


def run_reload() -> bool:
    script = find_admin_script()
    if script is None:
        raise FileNotFoundError(
            "unable to locate the repo-local admin wrapper; keep icepi_admin.py present or set ICEPI_ADMIN_SCRIPT"
        )
    command = admin_script_command(script, "reload")
    try:
        subprocess.run(command, check=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        from icepi.tools import render_command
        print(f"Reload failed. Run manually: {render_command(command)}")
        return False
