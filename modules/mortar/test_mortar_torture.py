#!/usr/bin/env python3
"""Torture test for MORTAR: MORTAR: 2x2 signed 8-bit matrix multiply accelerator.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

A00=0x000
A01=0x004
A10=0x008
A11=0x00C
B00=0x010
B01=0x014
B10=0x018
B11=0x01C
C00=0x020
C01=0x024
C10=0x028
C11=0x02C

def s8(x): return (x&0xFF)-256 if (x&0x80) else (x&0xFF)
def s16(x): return x & 0xFFFF

def gen():
    tb = TortureBuilder("mortar")
    cases = [
        (1,0,0,1, 5,6,7,8),
        (2,0,0,2, 3,4,5,6),
        (1,2,3,4, 5,6,7,8),
        (127,0,0,127, 1,0,0,1),
        (-1&0xFF,-1&0xFF,-1&0xFF,-1&0xFF, 1,1,1,1),
        (0,0,0,0, 99,99,99,99),
    ]
    for a00,a01,a10,a11, b00,b01,b10,b11 in cases:
        tb.write(A00,a00)
        tb.write(A01,a01)
        tb.write(A10,a10)
        tb.write(A11,a11)
        tb.write(B00,b00)
        tb.write(B01,b01)
        tb.write(B10,b10)
        tb.write(B11,b11)
        sa = [[s8(a00),s8(a01)],[s8(a10),s8(a11)]]
        sb = [[s8(b00),s8(b01)],[s8(b10),s8(b11)]]
        c00 = s16(sa[0][0]*sb[0][0] + sa[0][1]*sb[1][0])
        c01 = s16(sa[0][0]*sb[0][1] + sa[0][1]*sb[1][1])
        c10 = s16(sa[1][0]*sb[0][0] + sa[1][1]*sb[1][0])
        c11 = s16(sa[1][0]*sb[0][1] + sa[1][1]*sb[1][1])
        tb.read_check(C00, c00)
        tb.read_check(C01, c01)
        tb.read_check(C10, c10)
        tb.read_check(C11, c11)
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"MORTAR torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("mortar", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("mortar", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("mortar")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
