"""Flash layout loading, image planning, and layout rendering."""

from __future__ import annotations

import binascii
import hashlib
import json
from pathlib import Path

from icepi.models import FlashSlot, ImagePlan, LayoutConfig
from icepi.tools import REPO_ROOT, _align_up, _parse_int, strip_bitstream_header

__all__ = [
    "DEFAULT_LAYOUT_FILE",
    "load_layout",
    "plan_image",
    "render_layout_lines",
    "render_slots_lines",
    "render_plan_lines",
]

DEFAULT_LAYOUT_FILE = REPO_ROOT / "config" / "icepi-layout.json"


def load_layout(path: str | Path | None = None) -> LayoutConfig:
    """Load and parse the flash layout JSON file."""
    layout_path = Path(path or DEFAULT_LAYOUT_FILE).resolve()
    raw = json.loads(layout_path.read_text(encoding="utf-8"))
    slots: dict[str, FlashSlot] = {}
    aliases: dict[str, str] = {}
    for raw_name, raw_slot in raw["slots"].items():
        name = raw_name.strip().lower()
        slot = FlashSlot(
            name=name,
            offset=_parse_int(raw_slot["offset"]),
            size=_parse_int(raw_slot["size"]),
            bootable=bool(raw_slot.get("bootable", False)),
            writable=bool(raw_slot.get("writable", True)),
            description=raw_slot.get("description"),
            aliases=tuple(alias.strip().lower() for alias in raw_slot.get("aliases", [])),
            tags=tuple(tag.strip().lower() for tag in raw_slot.get("tags", [])),
        )
        slots[name] = slot
        aliases[name] = name
        for alias in slot.aliases:
            aliases[alias] = name
    for alias, target in raw.get("aliases", {}).items():
        aliases[alias.strip().lower()] = target.strip().lower()
    return LayoutConfig(
        path=layout_path,
        flash_size=_parse_int(raw["flash_size"]),
        default_slot=raw["default_slot"].strip().lower(),
        bundle_block_size=_parse_int(raw.get("bundle_block_size", 512)),
        slots=slots,
        aliases=aliases,
    )


def plan_image(
    bitstream_path: str | Path,
    *,
    layout: LayoutConfig,
    slot_name: str | None = None,
    address: int | None = None,
    reserved_bytes: int | None = None,
    chunk_size: int = 16,
    erase_size: int = 65536,
) -> ImagePlan:
    """Plan a flash write: resolve slot, compute padding, check fit.

    Returns an `ImagePlan` describing the target address, byte counts,
    CRC32, and SHA256 for the given bitstream and layout slot.
    """
    path = Path(bitstream_path).resolve()
    payload = strip_bitstream_header(path.read_bytes())
    if not payload:
        raise ValueError("bitstream is empty")
    padded_bytes = _align_up(len(payload), chunk_size)
    erase_bytes = _align_up(padded_bytes, erase_size)
    slot = None
    if slot_name is not None or address is None:
        slot = layout.resolve_slot(slot_name)
    base_address = slot.offset if slot is not None and address is None else int(address or 0)
    max_bytes = slot.size if slot is not None and reserved_bytes is None else reserved_bytes
    if base_address % erase_size != 0:
        raise ValueError(
            f"target address 0x{base_address:06X} is not aligned to erase size {erase_size}"
        )
    if max_bytes is not None and padded_bytes > max_bytes:
        raise ValueError(
            f"image needs {padded_bytes} bytes but target only reserves {max_bytes} bytes"
        )
    if (base_address + erase_bytes) > layout.flash_size:
        raise ValueError(
            f"image would end at 0x{base_address + erase_bytes:06X}, past flash size 0x{layout.flash_size:06X}"
        )
    return ImagePlan(
        bitstream_path=path,
        slot_name=slot.name if slot is not None else None,
        address=base_address,
        reserved_bytes=max_bytes,
        bitstream_bytes=len(payload),
        padded_bytes=padded_bytes,
        erase_bytes=erase_bytes,
        chunk_size=chunk_size,
        erase_size=erase_size,
        block_size=layout.bundle_block_size,
        crc32=binascii.crc32(payload) & 0xFFFFFFFF,
        sha256=hashlib.sha256(payload).hexdigest(),
        bootable=slot.bootable if slot is not None else False,
    )


def render_layout_lines(layout: LayoutConfig) -> list[str]:
    """Format flash layout and slot table as human-readable lines."""
    lines = [
        f"Layout: {layout.path}",
        f"Flash: {layout.flash_size} bytes",
        f"Default slot: {layout.default_slot}",
        f"Bundle block: {layout.bundle_block_size} bytes",
    ]
    for name in sorted(layout.slots):
        slot = layout.slots[name]
        tags = []
        if slot.bootable:
            tags.append("bootable")
        if slot.writable:
            tags.append("writable")
        if slot.tags:
            tags.extend(slot.tags)
        suffix = f" [{' '.join(tags)}]" if tags else ""
        lines.append(
            f"Slot {slot.name}: 0x{slot.offset:06X}-0x{slot.end - 1:06X} ({slot.size} bytes){suffix}"
        )
        if slot.aliases:
            lines.append("  Aliases: " + ", ".join(slot.aliases))
        if slot.description:
            lines.append("  " + slot.description)
    return lines


def render_slots_lines(layout: LayoutConfig) -> list[str]:
    """Format a concise one-line-per-slot table: range, size, flags, aliases."""
    lines = [f"Flash: {layout.flash_size // (1024 * 1024)} MB, default slot {layout.default_slot}"]
    for name in sorted(layout.slots):
        slot = layout.slots[name]
        flags = (["boot"] if slot.bootable else []) + ["rw" if slot.writable else "ro"]
        alias = ("  aka " + ", ".join(slot.aliases)) if slot.aliases else ""
        lines.append(
            f"  {slot.name:<8} 0x{slot.offset:06X}-0x{slot.end - 1:06X}  "
            f"{slot.size // 1024:>5} KB  [{','.join(flags)}]{alias}"
        )
    return lines


def render_plan_lines(plan: ImagePlan) -> list[str]:
    """Format an image plan (address, sizes, CRC) as human-readable lines."""
    lines = [
        f"Bitstream: {plan.bitstream_path}",
        f"Target address: 0x{plan.address:06X}",
        f"Bitstream bytes: {plan.bitstream_bytes}",
        f"Padded bytes: {plan.padded_bytes}",
        f"Erase coverage: {plan.erase_bytes}",
        f"Chunk size: {plan.chunk_size}",
        f"Erase size: {plan.erase_size}",
        f"CRC32: 0x{plan.crc32:08X}",
        f"SHA256: {plan.sha256}",
    ]
    if plan.slot_name is not None:
        lines.insert(1, f"Slot: {plan.slot_name}")
    if plan.reserved_bytes is not None:
        lines.insert(3, f"Reserved bytes: {plan.reserved_bytes}")
    if plan.bootable:
        lines.append("Bootable target: yes")
    return lines
