"""Verify per-module manifest LUT counts against a fresh nosis synthesis.

For every module with a buildable .sv source, synthesizes the module on its
own with nosis (no PnR), counts LUT4 cells in the emitted netlist, and
compares against the `resources.luts` field in module.json. Reports deltas;
with --update, rewrites the manifest's `luts` field to match the
freshly-measured value.

The compositor relies on the manifest sum vs the device cap with a 10%
margin; if a manifest lies, an apparently-valid composition could overflow
at PnR.

Usage:
    python scripts/verify_manifest_luts.py            # check (read-only)
    python scripts/verify_manifest_luts.py --update   # rewrite manifests
    python scripts/verify_manifest_luts.py --module anvil   # one module
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULES = REPO / "modules"


def list_modules() -> list[Path]:
    """Return module directories with at least one .sv source besides top.sv."""
    out = []
    for d in sorted(MODULES.iterdir()):
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        if d.name in ("compositions", "rime-i"):
            continue
        if not (d / "module.json").exists():
            continue
        sources = [f for f in d.glob("*.sv") if f.name != "top.sv"]
        if sources:
            out.append(d)
    return out


def synth_module(mod_dir: Path) -> int | None:
    """Synthesize the module's SV files with nosis and return the LUT4 count."""
    sources = sorted(f for f in mod_dir.glob("*.sv") if f.name != "top.sv")
    if not sources:
        return None
    # Coprocessor modules instantiate the shared CPU core; mirror the build
    # system's instantiation scan so standalone synthesis sees it.
    text = "\n".join(s.read_text(encoding="utf-8", errors="ignore") for s in sources)
    if "rime_i_core" in text:
        core = MODULES / "rime-i" / "rime_i_core.sv"
        if core.exists():
            sources.append(core)
    # Manifest may override the top module name (e.g. wire/wire.sv defines `wire_mod`).
    manifest = json.loads((mod_dir / "module.json").read_text(encoding="utf-8"))
    top_module = manifest.get("top_module", mod_dir.name.replace("-", "_"))
    with tempfile.TemporaryDirectory() as td:
        json_out = Path(td) / "netlist.json"
        result = subprocess.run(
            [sys.executable, "-m", "nosis", *[str(s) for s in sources],
             "--top", top_module, "-o", str(json_out)],
            capture_output=True, text=True, cwd=str(REPO), timeout=900, check=False,
        )
        if result.returncode != 0 or not json_out.exists():
            return None
        data = json.loads(json_out.read_text(encoding="utf-8"))
    luts = 0
    for mod in data.get("modules", {}).values():
        for cell in mod.get("cells", {}).values():
            if cell.get("type") == "LUT4":
                luts += 1
    return luts


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify module manifest LUT counts")
    parser.add_argument("--update", action="store_true", help="rewrite manifests with measured LUT counts")
    parser.add_argument("--module", help="run only this module")
    parser.add_argument("--tolerance", type=int, default=20, help="allowed percent delta before flagging")
    args = parser.parse_args()

    mods = list_modules()
    if args.module:
        mods = [m for m in mods if m.name == args.module]
        if not mods:
            print(f"unknown module: {args.module}", file=sys.stderr)
            return 1

    print(f"checking {len(mods)} modules")
    print(f"{'module':<14} {'declared':>9} {'measured':>9} {'delta':>8}")
    print("-" * 44)

    rows = []
    failed = 0
    for d in mods:
        manifest_path = d / "module.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest.get("resources", {}).get("luts", 0)
        measured = synth_module(d)
        if measured is None:
            print(f"{d.name:<14} {declared:>9d} {'FAIL':>9}")
            failed += 1
            continue
        delta_pct = 100.0 * (measured - declared) / max(declared, 1)
        marker = " *" if abs(delta_pct) > args.tolerance else ""
        print(f"{d.name:<14} {declared:>9d} {measured:>9d} {delta_pct:>+7.0f}%{marker}")
        rows.append((d, declared, measured, delta_pct))
        if args.update and measured != declared:
            manifest.setdefault("resources", {})["luts"] = measured
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    over_tolerance = sum(1 for _, _, _, d in rows if abs(d) > args.tolerance)
    print()
    print(f"checked: {len(rows)}, failed synth: {failed}, over {args.tolerance}% tolerance: {over_tolerance}")
    if args.update:
        updated = sum(1 for _, declared, measured, _ in rows if measured != declared)
        print(f"updated: {updated} manifests")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
