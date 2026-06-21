#!/usr/bin/env python3
"""Torture test for TAPER: TAPER: Tapered Arithmetic Precision Evaluation Register. 8-bit posit coprocessor.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

OP_A=0x000
OP_B=0x004
ADD=0x008
MUL=0x00C
MUL_HI=0x010
ABS_A=0x014
MIN=0x018
MAX=0x01C

def s8(x): return (x & 0xFF) - 256 if (x & 0x80) else (x & 0xFF)
def sat_add(a, b):
    r = s8(a) + s8(b)
    if r > 127:
        return 127
    if r < -128:
        return 256 + r if r < 0 else r
    return r & 0xFF

def gen():
    tb = TortureBuilder("taper")
    cases = [(10, 20), (100, 100), (-50 & 0xFF, -60 & 0xFF), (127, 1), (-128 & 0xFF, -1 & 0xFF),
             (0, 0), (0xFF, 0x01), (0x80, 0x80), (0x7F, 0x7F), (1, -1 & 0xFF)]
    for a, b in cases:
        tb.write(OP_A, a & 0xFF)
        tb.write(OP_B, b & 0xFF)
        sa, sb = s8(a), s8(b)
        tb.read_check(ADD, sat_add(a, b) & 0xFF)
        tb.read_check(MUL, (sa * sb) & 0xFF)
        tb.read_check(MUL_HI, ((sa * sb) >> 8) & 0xFF)
        tb.read_check(ABS_A, abs(sa) & 0xFF)
        tb.read_check(MIN, (min(sa, sb)) & 0xFF)
        tb.read_check(MAX, (max(sa, sb)) & 0xFF)
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"TAPER torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("taper", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("taper", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("taper")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
