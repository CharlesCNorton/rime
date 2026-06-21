#!/usr/bin/env python3
"""Run every module torture test offline (--gen-only).

Discovers test_*_torture.py under modules/, imports each, calls gen(),
and verifies the firmware fits in BRAM.

    python modules/torture_sweep.py
"""
import importlib.util
from pathlib import Path


def main() -> int:
    modules_root = Path(__file__).resolve().parent
    torture_files = sorted(modules_root.rglob("test_*_torture.py"))

    print(f"=== TORTURE SWEEP: {len(torture_files)} modules ===")

    passed = 0
    failed = 0
    for tf in torture_files:
        mod_name = tf.parent.name
        spec = importlib.util.spec_from_file_location(f"torture_{mod_name}", tf)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            if not hasattr(mod, "gen"):
                print(f"  {mod_name:12s} SKIP (no gen())")
                continue
            fw, expected = mod.gen()
            if len(fw) <= 1024:
                print(f"  {mod_name:12s} PASS  {len(fw):4d} instrs  hash=0x{expected:08X}")
                passed += 1
            else:
                print(f"  {mod_name:12s} FAIL  {len(fw):4d} instrs (exceeds 1024-word BRAM)")
                failed += 1
        except Exception as exc:
            print(f"  {mod_name:12s} FAIL  {exc}")
            failed += 1

    print(f"\nTORTURE SWEEP: {passed} passed, {failed} failed, {passed + failed} total")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
