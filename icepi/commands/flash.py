"""Flash read, JEDEC, status, clear-error, and verify commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from icepi.commands.helpers import (
    build_plan_for_args,
    ensure_service,
    explain_snapshot,
    load_layout_from_args,
    make_service,
    print_plan_header,
    print_service_mode_note,
    render_hexdump,
    resolved_as_dict,
    validate_flash_window,
)
from icepi.build import resolve_bitstream_target
from icepi.layout import render_plan_lines
from icepi.tools import make_progress_renderer, strip_bitstream_header

__all__ = [
    "cmd_clear_error",
    "cmd_flash_clear_error",
    "cmd_flash_jedec",
    "cmd_flash_status",
    "cmd_flash_read",
    "cmd_flash_verify",
]


def _clear_error_common(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        service.clear_last_error()
        snapshot = service.probe(auto_enter=False)
    print("Sticky error latch cleared.")
    for line in explain_snapshot(snapshot):
        print(line)
    print_service_mode_note(entered_service)
    return {
        "snapshot": snapshot.as_dict(),
        "entered_service": entered_service,
    }


def cmd_clear_error(args: argparse.Namespace) -> dict[str, object]:
    return _clear_error_common(args)


def cmd_flash_clear_error(args: argparse.Namespace) -> dict[str, object]:
    return _clear_error_common(args)


def cmd_flash_jedec(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        jedec = service.jedec()
        snapshot = service.probe(auto_enter=False)
    print("Flash JEDEC: " + " ".join(f"0x{value:02X}" for value in jedec))
    print_service_mode_note(entered_service)
    return {
        "jedec": [f"0x{value:02X}" for value in jedec],
        "snapshot": snapshot.as_dict(),
        "entered_service": entered_service,
    }


def cmd_flash_status(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        status = service.status()
        snapshot = service.probe(auto_enter=False)
    print(f"Status: sr1=0x{status[0]:02X} sr2=0x{status[1]:02X}")
    print_service_mode_note(entered_service)
    return {
        "status": {"sr1": f"0x{status[0]:02X}", "sr2": f"0x{status[1]:02X}"},
        "snapshot": snapshot.as_dict(),
        "entered_service": entered_service,
    }


def cmd_flash_read(args: argparse.Namespace) -> dict[str, object]:
    layout = load_layout_from_args(args)
    validate_flash_window(args.address, args.length, layout=layout)
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        data = service.read(args.address, args.length)
        snapshot = service.probe(auto_enter=False)
    if args.output:
        output = Path(args.output).resolve()
        output.write_bytes(data)
        print(f"Wrote {len(data)} bytes to {output}")
    else:
        for line in render_hexdump(data, base_address=args.address, width=args.hex_width):
            print(line)
    print_service_mode_note(entered_service)
    result: dict[str, object] = {
        "address": f"0x{args.address:06X}",
        "length": len(data),
        "snapshot": snapshot.as_dict(),
        "entered_service": entered_service,
    }
    if args.output:
        result["output"] = str(Path(args.output).resolve())
    else:
        result["data_hex"] = data.hex()
    return result


def cmd_flash_verify(args: argparse.Namespace) -> dict[str, object]:
    resolved = resolve_bitstream_target(
        args.target,
        build_if_project=args.build,
        clean=args.clean,
    )
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        info = service.info()
        _layout, plan = build_plan_for_args(
            resolved.bitstream,
            args,
            chunk_size=info.max_program,
            erase_size=info.erase_size,
        )
        print_plan_header(resolved)
        for line in render_plan_lines(plan):
            print(line)
        expected = strip_bitstream_header(resolved.bitstream.read_bytes())
        service.verify_bytes(
            plan.address,
            expected,
            progress=make_progress_renderer(args.verbose),
        )
        snapshot = service.probe(auto_enter=False)
    print(f"Verified {len(expected)} bytes against flash at 0x{plan.address:06X}")
    print_service_mode_note(entered_service)
    return {
        "resolved": resolved_as_dict(resolved),
        "plan": plan.as_dict(),
        "snapshot": snapshot.as_dict(),
        "entered_service": entered_service,
    }
