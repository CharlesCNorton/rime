#!/usr/bin/env python3
"""Torture test for RUNE: RUNE: 8x8 bitmap font renderer for ASCII 32-126.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("rune")
    tb.write(0x000, 32)
    tb.write(0x004, 0)
    tb.read_check(0x008, 0x00)
    tb.write(0x000, 65)
    tb.write(0x004, 0)
    tb.read_check(0x008, 0x18)
    tb.write(0x000, 65)
    tb.write(0x004, 3)
    tb.read_check(0x008, 0x7E)
    for ch in range(48, 58):
        tb.write(0x000, ch)
        tb.write(0x004, 0)
        tb.read_mix(0x008, None)
    tb.read_mix(0x00C, None)
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"RUNE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("rune", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("rune", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("rune")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
