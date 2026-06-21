"""SD card commands: info, init, layout, filesystem, bundles, auto-recovery."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from icepi.commands.helpers import (
    build_plan_for_args,
    ensure_service,
    make_service,
    print_plan_header,
    print_service_mode_note,
    render_hexdump,
    render_sd_info_lines,
    resolved_as_dict,
    validate_sd_window,
)
from icepi.build import FIRMWARE_ROOT, resolve_bitstream_target
from icepi.bundle import (
    build_bundle_bytes,
    bundle_header_from_bytes,
    parse_bundle_header,
    render_bundle_header_lines,
    validate_bundle_header,
)
from icepi.flash_service import FlashServiceError
from icepi.layout import render_plan_lines
from icepi.models import (
    AUTO_CONTROL_LBA,
    AUTO_RESULT_PENDING,
    BUNDLE_HEADER_BYTES,
    ImagePlan,
    ResolvedBitstream,
)
from icepi.sd import (
    FatFilesystem,
    build_auto_control_block,
    load_fat_volume,
    parse_sd_partitions,
    read_auto_control_block,
    read_sd_bytes,
    render_auto_control_lines,
    render_fat_directory_lines,
    render_fat_volume_lines,
    render_sd_layout_lines,
    stage_bundle_to_sd,
    write_auto_control_block,
)

__all__ = [
    "cmd_sd_info",
    "cmd_sd_init",
    "cmd_sd_layout",
    "cmd_sd_fs_info",
    "cmd_sd_fs_ls",
    "cmd_sd_fs_cat",
    "cmd_sd_read",
    "cmd_sd_bundle_info",
    "cmd_sd_install",
    "cmd_sd_stage_bundle",
    "cmd_sd_auto_info",
    "cmd_sd_auto_clear",
    "cmd_sd_auto_arm",
]


def cmd_sd_info(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        sd_info = service.sd_info()
        snapshot = service.probe(auto_enter=False)
    for line in render_sd_info_lines(sd_info):
        print(line)
    print_service_mode_note(entered_service)
    return {"sd_info": asdict(sd_info), "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_init(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        sd_info = service.sd_init()
        snapshot = service.probe(auto_enter=False)
    print("SD init completed.")
    for line in render_sd_info_lines(sd_info):
        print(line)
    print_service_mode_note(entered_service)
    return {"sd_info": asdict(sd_info), "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_layout(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        block0 = read_sd_bytes(service, lba=0, length=512)
        partitions = parse_sd_partitions(block0)
        snapshot = service.probe(auto_enter=False)
    for line in render_sd_layout_lines(partitions):
        print(line)
    print_service_mode_note(entered_service)
    return {"partitions": [entry.as_dict() for entry in partitions], "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_fs_info(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        volume = load_fat_volume(service, partition_index=args.partition)
        snapshot = service.probe(auto_enter=False)
    for line in render_fat_volume_lines(volume):
        print(line)
    print_service_mode_note(entered_service)
    return {"volume": volume.as_dict(), "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_fs_ls(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        volume = load_fat_volume(service, partition_index=args.partition)
        fs = FatFilesystem(service, volume)
        target = fs.resolve(args.path)
        if target is not None and not target.is_dir:
            raise ValueError(f"`{args.path}` is not a directory")
        cluster = volume.root_cluster if target is None else (target.first_cluster or volume.root_cluster)
        entries = fs.list_directory(cluster)
        snapshot = service.probe(auto_enter=False)
    for line in render_fat_directory_lines(args.path, entries):
        print(line)
    print_service_mode_note(entered_service)
    return {"path": args.path, "volume": volume.as_dict(), "entries": [entry.as_dict() for entry in entries], "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_fs_cat(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        volume = load_fat_volume(service, partition_index=args.partition)
        fs = FatFilesystem(service, volume)
        data = fs.read_file(args.path)
        snapshot = service.probe(auto_enter=False)
    if args.output:
        output = Path(args.output).resolve()
        output.write_bytes(data)
        print(f"Wrote {len(data)} bytes to {output}")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            for line in render_hexdump(data, base_address=0, width=args.hex_width):
                print(line)
        else:
            print(text, end="" if text.endswith("\n") else "\n")
    print_service_mode_note(entered_service)
    result: dict[str, object] = {"path": args.path, "volume": volume.as_dict(), "length": len(data), "snapshot": snapshot.as_dict(), "entered_service": entered_service}
    if args.output:
        result["output"] = str(Path(args.output).resolve())
    else:
        result["data_hex"] = data.hex()
    return result


def cmd_sd_read(args: argparse.Namespace) -> dict[str, object]:
    validate_sd_window(args.offset, args.length)
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        data = service.sd_read(args.lba, offset=args.offset, length=args.length)
        snapshot = service.probe(auto_enter=False)
    if args.output:
        output = Path(args.output).resolve()
        output.write_bytes(data)
        print(f"Wrote {len(data)} bytes to {output}")
    else:
        for line in render_hexdump(data, base_address=args.offset, width=args.hex_width):
            print(line)
    print_service_mode_note(entered_service)
    result: dict[str, object] = {"lba": args.lba, "offset": args.offset, "length": len(data), "snapshot": snapshot.as_dict(), "entered_service": entered_service}
    if args.output:
        result["output"] = str(Path(args.output).resolve())
    else:
        result["data_hex"] = data.hex()
    return result


def cmd_sd_bundle_info(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        header_bytes = read_sd_bytes(service, lba=args.lba, length=BUNDLE_HEADER_BYTES)
        header = parse_bundle_header(header_bytes)
        try:
            validate_bundle_header(header)
        except ValueError as exc:
            raise FlashServiceError(f"SD block {args.lba} does not contain a valid RIME bundle header ({exc})") from exc
        manifest_obj: Any | None = None
        manifest_text: str | None = None
        if args.manifest:
            manifest_bytes = read_sd_bytes(service, lba=args.lba, offset=BUNDLE_HEADER_BYTES, length=header.manifest_bytes)
            manifest_text = manifest_bytes.decode("utf-8")
            manifest_obj = json.loads(manifest_text)
        snapshot = service.probe(auto_enter=False)
    for line in render_bundle_header_lines(header, base_lba=args.lba):
        print(line)
    if manifest_obj is not None:
        print("Manifest:")
        print(json.dumps(manifest_obj, indent=2, sort_keys=True))
    print_service_mode_note(entered_service)
    result: dict[str, object] = {"lba": args.lba, "bundle": header.as_dict(), "snapshot": snapshot.as_dict(), "entered_service": entered_service}
    if manifest_obj is not None:
        result["manifest"] = manifest_obj
    elif manifest_text is not None:
        result["manifest_text"] = manifest_text
    return result


def cmd_sd_install(args: argparse.Namespace) -> dict[str, object]:
    from icepi.commands.helpers import run_reload
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        service.sd_install(args.lba, timeout=args.timeout)
        snapshot = service.probe(auto_enter=False)
    print(f"Installed bundle from SD LBA {args.lba}.")
    if args.reload:
        print("Reloading from flash.")
        run_reload()
    else:
        print("Note: board remains in service mode until `reload` restores the resident app.")
    return {"lba": args.lba, "timeout": args.timeout, "snapshot": snapshot.as_dict(), "entered_service": entered_service, "reloaded": args.reload}


def cmd_sd_stage_bundle(args: argparse.Namespace) -> dict[str, object]:
    resolved = resolve_bitstream_target(args.target, build_if_project=args.build, clean=args.clean)
    layout, plan = build_plan_for_args(resolved.bitstream, args, chunk_size=16, erase_size=65536)
    bundle_bytes, manifest = build_bundle_bytes(plan, layout=layout)
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        stage_lba, block_count = stage_bundle_to_sd(service, bundle_bytes=bundle_bytes, requested_lba=args.lba, no_verify=args.no_verify, verbose=args.verbose)
        print_plan_header(resolved)
        for line in render_plan_lines(plan):
            print(line)
        print(f"Bundle bytes: {len(bundle_bytes)}")
        print(f"Bundle blocks: {block_count}")
        print(f"Staging LBA: {stage_lba}")
        snapshot = service.probe(auto_enter=False)
    print(f"Staged bundle for {resolved.label} at SD LBA {stage_lba}.")
    print_service_mode_note(entered_service)
    return {"resolved": resolved_as_dict(resolved), "plan": plan.as_dict(), "bundle_bytes": len(bundle_bytes), "bundle_blocks": block_count, "staging_lba": stage_lba, "manifest": manifest, "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_auto_info(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        block = read_auto_control_block(service, lba=args.lba)
        snapshot = service.probe(auto_enter=False)
    for line in render_auto_control_lines(block):
        print(line)
    print_service_mode_note(entered_service)
    return {"control": block.as_dict(), "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_auto_clear(args: argparse.Namespace) -> dict[str, object]:
    block = build_auto_control_block(attempt_limit=0, armed=False, clear_on_success=True, fallback_on_fail=False, lba=args.lba)
    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        write_auto_control_block(service, block)
        snapshot = service.probe(auto_enter=False)
    print(f"Cleared auto-repair control block at SD LBA {args.lba}.")
    print_service_mode_note(entered_service)
    return {"control": block.as_dict(), "snapshot": snapshot.as_dict(), "entered_service": entered_service}


def cmd_sd_auto_arm(args: argparse.Namespace) -> dict[str, object]:
    primary = resolve_bitstream_target(args.target, build_if_project=args.build or Path(args.target).expanduser().is_dir() or (FIRMWARE_ROOT / args.target).is_dir(), clean=args.clean)
    layout, primary_plan = build_plan_for_args(primary.bitstream, args, chunk_size=16, erase_size=65536)
    primary_bundle_bytes, primary_manifest = build_bundle_bytes(primary_plan, layout=layout)
    primary_header = bundle_header_from_bytes(primary_bundle_bytes)

    fallback: ResolvedBitstream | None = None
    fallback_plan: ImagePlan | None = None
    fallback_bundle_bytes: bytes | None = None
    fallback_header = None
    fallback_manifest: dict[str, Any] | None = None
    if args.fallback_target:
        fallback = resolve_bitstream_target(args.fallback_target, build_if_project=args.build or Path(args.fallback_target).expanduser().is_dir() or (FIRMWARE_ROOT / args.fallback_target).is_dir(), clean=args.clean)
        fallback_namespace = argparse.Namespace(**vars(args))
        fallback_namespace.slot = args.fallback_slot
        _fallback_layout, fallback_plan = build_plan_for_args(fallback.bitstream, fallback_namespace, chunk_size=16, erase_size=65536)
        fallback_bundle_bytes, fallback_manifest = build_bundle_bytes(fallback_plan, layout=layout)
        fallback_header = bundle_header_from_bytes(fallback_bundle_bytes)

    if args.attempt_limit < 1:
        raise ValueError("attempt limit must be at least 1")

    with make_service(args) as service:
        _snapshot, entered_service = ensure_service(service)
        print_plan_header(primary)
        for line in render_plan_lines(primary_plan):
            print(line)
        primary_lba, primary_blocks = stage_bundle_to_sd(service, bundle_bytes=primary_bundle_bytes, requested_lba=args.lba, no_verify=args.no_verify, verbose=args.verbose)
        fallback_lba = 0
        fallback_blocks = 0
        if fallback is not None and fallback_plan is not None and fallback_bundle_bytes is not None:
            print_plan_header(fallback)
            for line in render_plan_lines(fallback_plan):
                print(line)
            fallback_lba, fallback_blocks = stage_bundle_to_sd(service, bundle_bytes=fallback_bundle_bytes, requested_lba=args.fallback_lba, no_verify=args.no_verify, verbose=args.verbose, reserved_ranges=[(primary_lba, primary_lba + primary_blocks - 1)])
        control = build_auto_control_block(primary_lba=primary_lba, fallback_lba=fallback_lba, attempt_limit=args.attempt_limit, attempt_count=0, last_result=AUTO_RESULT_PENDING, last_source_lba=0, last_bundle_crc32=primary_header.crc32, armed=True, clear_on_success=not args.keep_armed, fallback_on_fail=not args.no_fallback_on_fail, lba=AUTO_CONTROL_LBA)
        write_auto_control_block(service, control)
        snapshot = service.probe(auto_enter=False)
    print(f"Armed SD auto-repair control block at LBA {control.lba}.")
    print(f"Primary bundle LBA: {primary_lba}")
    if fallback_lba:
        print(f"Fallback bundle LBA: {fallback_lba}")
    print_service_mode_note(entered_service)
    result: dict[str, object] = {"control": control.as_dict(), "primary": {"resolved": resolved_as_dict(primary), "plan": primary_plan.as_dict(), "bundle": primary_header.as_dict(), "manifest": primary_manifest, "lba": primary_lba, "blocks": primary_blocks}, "snapshot": snapshot.as_dict(), "entered_service": entered_service}
    if fallback is not None and fallback_plan is not None and fallback_header is not None and fallback_manifest is not None:
        result["fallback"] = {"resolved": resolved_as_dict(fallback), "plan": fallback_plan.as_dict(), "bundle": fallback_header.as_dict(), "manifest": fallback_manifest, "lba": fallback_lba, "blocks": fallback_blocks}
    return result
