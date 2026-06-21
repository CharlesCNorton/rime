"""Layout and slot commands for the icepi_helper CLI.

Implements the `layout` and `plan` subcommands: display the flash
slot map from config/icepi-layout.json, resolve slot aliases, and
compute image plans (padding, erase coverage, CRC, SHA256) for a
given bitstream and target slot.
"""

from __future__ import annotations

import argparse

from icepi.commands.helpers import load_layout_from_args
from icepi.layout import render_layout_lines, render_slots_lines

__all__ = ["cmd_layout", "cmd_slots", "cmd_slot_show"]


def cmd_layout(args: argparse.Namespace) -> dict[str, object]:
    layout = load_layout_from_args(args)
    for line in render_layout_lines(layout):
        print(line)
    return {"layout": layout.as_dict()}


def cmd_slots(args: argparse.Namespace) -> dict[str, object]:
    layout = load_layout_from_args(args)
    for line in render_slots_lines(layout):
        print(line)
    return {"layout": layout.as_dict()}


def cmd_slot_show(args: argparse.Namespace) -> dict[str, object]:
    layout = load_layout_from_args(args)
    slot = layout.resolve_slot(args.slot)
    tags = []
    if slot.bootable:
        tags.append("bootable")
    if slot.writable:
        tags.append("writable")
    if slot.tags:
        tags.extend(slot.tags)
    print(f"Slot: {slot.name}")
    print(f"Range: 0x{slot.offset:06X}-0x{slot.end - 1:06X}")
    print(f"Size: {slot.size} bytes")
    if tags:
        print("Flags: " + ", ".join(tags))
    if slot.aliases:
        print("Aliases: " + ", ".join(slot.aliases))
    if slot.description:
        print(slot.description)
    return {"slot": slot.as_dict()}
