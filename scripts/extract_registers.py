#!/usr/bin/env python3
"""Lift per-module register maps from .sv header comments into module.json.

Each module documents its register map as a prose comment block at the top
of its primary .sv file, in one of two house styles:

    //   0x000: DATA    (write) — feed one byte
    //   0x004  STATUS      (R)  status word

This script parses that block into a machine-readable ``registers`` array:

    "registers": [
      {"offset": "0x000", "name": "DATA", "access": "w", "desc": "feed one byte"},
      ...
    ]

so that ``icepi_helper.py digest`` is complete down to the register level and
agents never have to open a .sv to learn a module's register layout.

The .sv comment stays the human-facing source; this keeps the JSON in sync.
A ``--check`` run (read-only, nonzero exit on drift) is meant to sit in CI next
to scripts/verify_manifest_luts.py.

Usage:
    python scripts/extract_registers.py            # dry-run: show what would change
    python scripts/extract_registers.py --write    # rewrite module.json files
    python scripts/extract_registers.py --check     # CI: fail if JSON != source
    python scripts/extract_registers.py --module anvil
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULES = REPO / "modules"

# CPUs and the compositor describe a memory map, not a peripheral register map.
SKIP = {"compositions", "rime-i", "rime-ii"}

# One register line. Tolerant of both house styles:
#   "0x000: NAME (write) — desc"   and   "0x000  NAME  (R)  desc"
# plus ranges ("0x000-0x01C") and parametric offsets ("0x100+N*4").
_LINE = re.compile(
    r"^\s*//\s*"
    r"(?P<off>0x[0-9A-Fa-f]+(?:\s*-\s*0x[0-9A-Fa-f]+|\s*\+\s*[0-9A-Za-z*]+)?)"
    r"\s*:?\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_\[\].]*)"
    r"\s*\((?P<acc>[^)]+)\)"
    r"(?P<rest>.*)$"
)

# Strip the separator that leads a description: em/en dashes, hyphen, colon,
# pipe, or whitespace. Robust to the mojibake dash in rune.sv's header.
_DESC_LEAD = re.compile(r"^[\s:|‒-―\-]+")


def _normalize_access(raw: str) -> str:
    """Fold the access notation to r / w / rw, or pass through if unrecognized."""
    a = raw.strip().lower().replace(" ", "")
    if a in ("r", "ro", "read", "readonly"):
        return "r"
    if a in ("w", "wo", "write", "writeonly"):
        return "w"
    if a in ("rw", "wr", "r/w", "w/r", "read/write", "write/read", "readwrite"):
        return "rw"
    return raw.strip()


def _primary_source(mod_dir: Path) -> Path | None:
    """The .sv file holding the register-map comment: <name>.sv, else any non-top .sv."""
    named = mod_dir / f"{mod_dir.name}.sv"
    if named.exists():
        return named
    candidates = [f for f in sorted(mod_dir.glob("*.sv")) if f.name != "top.sv"]
    return candidates[0] if candidates else None


def parse_registers(sv_path: Path) -> list[dict[str, str]]:
    """Extract the register table from a module's .sv header comment block.

    Only the comment lines preceding the ``module`` declaration are scanned, so
    body comments cannot leak in as false positives.
    """
    regs: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in sv_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("module ", "module\t")):
            break
        m = _LINE.match(line)
        if not m:
            continue
        offset = re.sub(r"\s+", "", m.group("off"))
        name = m.group("name")
        key = f"{offset}:{name}"
        if key in seen:
            continue
        seen.add(key)
        entry = {"offset": offset, "name": name, "access": _normalize_access(m.group("acc"))}
        desc = _DESC_LEAD.sub("", m.group("rest")).strip()
        if desc:
            entry["desc"] = desc
        regs.append(entry)
    return regs


def module_dirs(only: str | None) -> list[Path]:
    out = []
    for d in sorted(MODULES.iterdir()):
        if not d.is_dir() or d.name in SKIP or d.name.startswith((".", "_")):
            continue
        if not (d / "module.json").exists():
            continue
        if only and d.name != only:
            continue
        out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Lift register maps from .sv comments into module.json")
    ap.add_argument("--write", action="store_true", help="rewrite module.json files in place")
    ap.add_argument("--check", action="store_true", help="CI mode: exit 1 if any module.json is out of sync")
    ap.add_argument("--module", help="operate on a single module")
    args = ap.parse_args()

    dirs = module_dirs(args.module)
    if not dirs:
        print("no modules matched", file=sys.stderr)
        return 1

    drift = 0
    empty = []
    print(f"{'module':<14} {'regs':>4}  status")
    print("-" * 40)
    for d in dirs:
        mj_path = d / "module.json"
        manifest = json.loads(mj_path.read_text(encoding="utf-8"))
        sv = _primary_source(d)
        regs = parse_registers(sv) if sv else []
        if not regs:
            empty.append(d.name)
        current = manifest.get("registers")
        in_sync = current == regs

        if args.check:
            status = "ok" if in_sync else "DRIFT"
            if not in_sync:
                drift += 1
        elif args.write:
            if in_sync:
                status = "unchanged"
            else:
                manifest["registers"] = regs
                mj_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                status = "written"
        else:
            status = "in sync" if in_sync else "would update"
        print(f"{d.name:<14} {len(regs):>4}  {status}")

    print()
    if empty:
        print(f"NOTE: no registers parsed for: {', '.join(empty)} "
              f"(non-standard header — check the .sv comment or extend the parser)")
    if args.check and drift:
        print(f"CHECK FAILED: {drift} module.json file(s) out of sync with source — "
              f"run `python scripts/extract_registers.py --write`", file=sys.stderr)
        return 1
    if args.check:
        print(f"CHECK OK: {len(dirs)} modules in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
