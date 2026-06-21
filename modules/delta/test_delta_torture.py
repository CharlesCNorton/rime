#!/usr/bin/env python3
"""Torture test for DELTA: DELTA: byte-stream XOR differencing engine.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

OLD=0x000
NEW=0x004
DIFF=0x008
CHANGED=0x00C
TOTAL=0x010
CTRL=0x014
SAME=0x018

def gen():
    tb = TortureBuilder("delta")
    tb.reset(CTRL, bit=0)
    tb.read_check(CHANGED, 0)
    tb.read_check(TOTAL, 0)
    tb.read_check(SAME, 0)
    pairs = [(0x41, 0x41), (0x42, 0x43), (0xFF, 0x00), (0x00, 0x00), (0x80, 0x7F)]
    changed, same = 0, 0
    for old, new in pairs:
        tb.write(OLD, old)
        tb.write(NEW, new)
        tb.read_check(DIFF, old ^ new)
        if old != new:
            changed += 1
        else:
            same += 1
    tb.read_check(CHANGED, changed)
    tb.read_check(SAME, same)
    tb.read_check(TOTAL, len(pairs))
    tb.reset(CTRL, bit=0)
    tb.read_check(CHANGED, 0)
    tb.adversarial_write(OLD, 0xFFFFFFFF)
    tb.adversarial_write(NEW, 0xFFFFFFFF)
    tb.read_check(DIFF, 0)
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"DELTA torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("delta", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("delta", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("delta")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
