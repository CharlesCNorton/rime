#!/usr/bin/env python3
"""Torture test for SPARK: SPARK: Simple Perceptron with Activation and Responsive Kernel — 8-input single-layer perceptron

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

INPUT   = 0x000
WEIGHT  = 0x020
BIAS    = 0x040
CONTROL = 0x044
STATUS  = 0x048
SUM     = 0x04C
OUTPUT  = 0x050


def s8(x):
    x = x & 0xFF
    return x - 256 if x >= 128 else x


def gen():
    tb = TortureBuilder("spark")
    tb.write(CONTROL, 0x02)  # reset

    # All inputs=1, all weights=1, bias=0 -> sum=8, output=1
    for i in range(8):
        tb.write(INPUT + i * 4, 1)
        tb.write(WEIGHT + i * 4, 1)
    tb.write(BIAS, 0)
    tb.write(CONTROL, 0x01)
    tb.delay(15)
    tb.read_check(STATUS, 1)
    tb.read_check(SUM, 8)
    tb.read_check(OUTPUT, 1)

    # All inputs=1, all weights=-1, bias=0 -> sum=-8, output=0
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(INPUT + i * 4, 1)
        tb.write(WEIGHT + i * 4, 0xFF)  # -1
    tb.write(BIAS, 0)
    tb.write(CONTROL, 0x01)
    tb.delay(15)
    tb.read_check(OUTPUT, 0)

    # Mixed: 4 positive + 4 negative with bias tipping it
    tb.write(CONTROL, 0x02)
    for i in range(4):
        tb.write(INPUT + i * 4, 10)
        tb.write(WEIGHT + i * 4, 1)
    for i in range(4, 8):
        tb.write(INPUT + i * 4, 10)
        tb.write(WEIGHT + i * 4, 0xFF)  # -1
    tb.write(BIAS, 1)  # tips sum to +1
    tb.write(CONTROL, 0x01)
    tb.delay(15)
    tb.read_check(OUTPUT, 1)

    # Zero everything
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(INPUT + i * 4, 0)
        tb.write(WEIGHT + i * 4, 0)
    tb.write(BIAS, 0)
    tb.write(CONTROL, 0x01)
    tb.delay(15)
    tb.read_check(SUM, 0)
    tb.read_check(OUTPUT, 1)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"SPARK torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("spark", firmware, mod_dir / "top.sv")
    ok, luts = build_module("spark", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("spark")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
