"""`digest` command: a machine-readable index of the repository's structure.

The repo is ~30K tokens of patterns instantiated hundreds of times. Rather
than walk the tree and read 450 files, an agent (or a human) runs

    icepi_helper.py digest            # human summary
    icepi_helper.py digest --json     # full machine-readable index
    icepi_helper.py digest anvil      # one module's register map

This aggregates what is already single-sourced elsewhere — the protocol tables
(icepi/protocol.py), the flash/SDRAM memory map (config/icepi-layout.json plus
the addressable-window constants), the compositor budget (icepi/compose.py), and
the module registry (modules/*/module.json, including the register maps lifted in
by scripts/extract_registers.py). Nothing here touches the board; it is pure
repository introspection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from icepi import protocol as P
from icepi.commands.helpers import CommandParseError
from icepi.compose import (
    DEVICE_BRAMS,
    DEVICE_LUTS,
    DEVICE_MULTS,
    MARGIN_PERCENT,
    PLATFORM_OVERHEAD_LUTS,
    RIME_I_BRAMS,
    RIME_I_LUTS,
)
from icepi.flash_service import FLASH_SIZE_BYTES, SDRAM_WORD_COUNT
from icepi.layout import DEFAULT_LAYOUT_FILE
from icepi.tools import REPO_ROOT

__all__ = ["cmd_digest", "build_digest"]

MODULES_ROOT = REPO_ROOT / "modules"
NON_MODULE_DIRS = {"compositions"}


def _constants_with_prefix(prefix: str) -> dict[str, int]:
    """Collect int constants from icepi.protocol whose name starts with *prefix*."""
    out: dict[str, int] = {}
    for name in dir(P):
        if name.startswith(prefix):
            value = getattr(P, name)
            if isinstance(value, int):
                out[name] = value
    return out


def _protocol_digest() -> dict[str, Any]:
    """Command bytes, error codes, capability bits, and debug flags, single-sourced."""
    commands = {
        f"0x{v:02X}": P.command_name(v)
        for v in sorted(_constants_with_prefix("CMD_").values())
    }
    errors = {
        f"0x{v:02X}": P.error_name(v)
        for v in sorted(_constants_with_prefix("ERR_").values())
    }
    caps0 = {name[len("CAPS0_"):].lower(): f"0x{v:02X}"
             for name, v in sorted(_constants_with_prefix("CAPS0_").items(), key=lambda kv: kv[1])}
    caps1 = {name[len("CAPS1_"):].lower(): f"0x{v:02X}"
             for name, v in sorted(_constants_with_prefix("CAPS1_").items(), key=lambda kv: kv[1])}
    debug_flags = {name[len("DEBUG_FLAG_"):].lower(): f"0x{v:02X}"
                   for name, v in sorted(_constants_with_prefix("DEBUG_FLAG_").items(), key=lambda kv: kv[1])}
    return {
        "command_count": len(commands),
        "commands": commands,
        "errors": errors,
        "caps0": caps0,
        "caps1": caps1,
        "debug_flags": debug_flags,
        "framing": {
            "baud": 115200,
            "crc8_poly": "0x07",
            "error_frame": "[0xFF, code, state_hi, state_lo, command, detail, flags, spi_op]",
        },
    }


def _memory_digest(layout_path: Path) -> dict[str, Any]:
    """Flash slot map (+ SDRAM windows) from the layout JSON and window constants."""
    raw = json.loads(layout_path.read_text(encoding="utf-8"))
    slots = {}
    for name, slot in raw.get("slots", {}).items():
        slots[name] = {
            "offset": slot["offset"],
            "size": slot["size"],
            "bootable": bool(slot.get("bootable", False)),
            "writable": bool(slot.get("writable", True)),
        }
    return {
        "flash_bytes": FLASH_SIZE_BYTES,
        "sdram_words": SDRAM_WORD_COUNT,
        "sdram_bytes": SDRAM_WORD_COUNT * 2,
        "default_slot": raw.get("default_slot"),
        "bundle_block_size": raw.get("bundle_block_size"),
        "slots": slots,
        "aliases": raw.get("aliases", {}),
        "sdram": raw.get("sdram", {}),
    }


def _module_registry() -> list[dict[str, Any]]:
    """Every modules/*/module.json, with the lifted register maps."""
    mods: list[dict[str, Any]] = []
    for mod_dir in sorted(MODULES_ROOT.iterdir()):
        if not mod_dir.is_dir() or mod_dir.name in NON_MODULE_DIRS:
            continue
        mj = mod_dir / "module.json"
        if not mj.exists():
            continue
        data = json.loads(mj.read_text(encoding="utf-8"))
        resources = data.get("resources", {})
        interfaces = data.get("interfaces", {})
        requires = [r.lower() for r in interfaces.get("requires", [])]
        registers = data.get("registers", [])
        mods.append({
            "name": data.get("name", mod_dir.name),
            "description": data.get("description", ""),
            "top_module": data.get("top_module", mod_dir.name),
            "luts": resources.get("luts", 0),
            "brams": resources.get("brams", 0),
            "mults": resources.get("multipliers", 0),
            "requires": requires,
            "provides": interfaces.get("provides", []),
            "snoop": "snoop" in requires,
            "register_count": len(registers),
            "registers": registers,
        })
    return mods


def build_digest(layout_path: Path) -> dict[str, Any]:
    """Assemble the full repository digest dict."""
    modules = _module_registry()
    return {
        "board": "IcePi Zero (Lattice ECP5U-25F, CABGA256)",
        "sys_clock_hz": 25000000,
        "protocol": _protocol_digest(),
        "memory": _memory_digest(layout_path),
        "compositor": {
            "device_luts": DEVICE_LUTS,
            "device_brams": DEVICE_BRAMS,
            "device_mults": DEVICE_MULTS,
            "rime_i_luts": RIME_I_LUTS,
            "rime_i_brams": RIME_I_BRAMS,
            "platform_overhead_luts": PLATFORM_OVERHEAD_LUTS,
            "margin_percent": MARGIN_PERCENT,
            "usable_luts": DEVICE_LUTS - DEVICE_LUTS * MARGIN_PERCENT // 100,
            "max_modules": 16,
            "address_region": "0x30-0x3F",
        },
        "module_count": len(modules),
        "modules": modules,
    }


def _print_human(digest: dict[str, Any], focus: str | None) -> None:
    if focus is not None:
        mod = next(m for m in digest["modules"] if m["name"] == focus)
        print(f"{mod['name']}  —  {mod['description']}")
        print(f"  top_module={mod['top_module']}  luts={mod['luts']} brams={mod['brams']} "
              f"mults={mod['mults']}  requires={','.join(mod['requires'])}")
        if not mod["registers"]:
            print("  (no register map in source header)")
            return
        print(f"  {'offset':<10} {'acc':<3} {'name':<14} description")
        for r in mod["registers"]:
            print(f"  {r['offset']:<10} {r.get('access',''):<3} {r['name']:<14} {r.get('desc','')}")
        return

    proto = digest["protocol"]
    mem = digest["memory"]
    comp = digest["compositor"]
    print(f"Board: {digest['board']}  @ {digest['sys_clock_hz'] // 1_000_000} MHz")
    print(f"Protocol: {proto['command_count']} commands, {len(proto['errors'])} error codes, "
          f"CRC-8 framing (poly {proto['framing']['crc8_poly']})")
    print(f"Flash: {mem['flash_bytes'] // (1024*1024)} MB in {len(mem['slots'])} slots "
          f"({', '.join(mem['slots'])});  SDRAM: {mem['sdram_bytes'] // (1024*1024)} MB")
    print(f"Compositor: {comp['usable_luts']} usable LUT4 "
          f"({comp['margin_percent']}% margin of {comp['device_luts']}), "
          f"RIME-I costs {comp['rime_i_luts']} + {comp['platform_overhead_luts']} overhead; "
          f"up to {comp['max_modules']} modules at {comp['address_region']}")
    print(f"Modules: {digest['module_count']}")
    print()
    print(f"  {'name':<13} {'luts':>5} {'bram':>4} {'snoop':>5} {'regs':>4}  description")
    print("  " + "-" * 76)
    for m in digest["modules"]:
        desc = m["description"]
        if len(desc) > 40:
            desc = desc[:39] + "…"
        print(f"  {m['name']:<13} {m['luts']:>5} {m['brams']:>4} "
              f"{'•' if m['snoop'] else ' ':>5} {m['register_count']:>4}  {desc}")
    print()
    print("Run `digest <module>` for a register map, or `digest --json` for the full index.")


def cmd_digest(args: argparse.Namespace) -> dict[str, object]:
    """Emit the repository digest (human summary, --json, or a single module)."""
    layout_path = Path(getattr(args, "layout", None) or DEFAULT_LAYOUT_FILE)
    digest = build_digest(layout_path)
    focus = getattr(args, "module", None)
    if focus is not None:
        mod = next((m for m in digest["modules"] if m["name"] == focus), None)
        if mod is None:
            known = ", ".join(m["name"] for m in digest["modules"])
            raise CommandParseError(f"unknown module `{focus}` (known: {known})", status=1)
        if getattr(args, "json", False):
            print(json.dumps(mod, indent=2))
        else:
            _print_human(digest, focus)
        return digest
    if getattr(args, "json", False):
        print(json.dumps(digest, indent=2))
        return digest
    _print_human(digest, None)
    return digest
