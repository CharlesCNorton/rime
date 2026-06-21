#!/usr/bin/env python3
"""Torture test for WEAVE: WEAVE: bit-serial arithmetic unit. Trades time for area.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder, u32

OP_A=0x000
OP_B=0x004
CMD=0x008
RESULT=0x00C
STATUS=0x010

def gen():
    tb = TortureBuilder("weave")
    cases = [
        (0, 100, 200, u32(100+200)),
        (1, 200, 100, u32(200-100)),
        (2, 7, 6, u32(7*6)),
        (3, 0xFF00FF00, 0x0F0F0F0F, 0x0F000F00),
        (4, 0xFF00FF00, 0x0F0F0F0F, 0xFF0FFF0F),
        (5, 0xAAAAAAAA, 0x55555555, 0xFFFFFFFF),
    ]
    for cmd, a, b, expected in cases:
        tb.write(OP_A, a)
        tb.write(OP_B, b)
        tb.write(CMD, cmd)
        tb.delay(50)
        tb.read_check(RESULT, expected)
    tb.adversarial_write(OP_A, 0xFFFFFFFF)
    tb.adversarial_write(OP_B, 0xFFFFFFFF)
    tb.write(CMD, 0)
    tb.delay(50)
    tb.read_check(RESULT, u32(0xFFFFFFFF + 0xFFFFFFFF))
    tb.write(CMD, 2)
    tb.delay(50)
    tb.read_mix(RESULT, None)
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"WEAVE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("weave", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("weave", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("weave")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
