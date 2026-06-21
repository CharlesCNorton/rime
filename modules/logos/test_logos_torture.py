#!/usr/bin/env python3
"""LOGOS torture test.

Validates log2 of powers of two in 8.8 fixed-point format. The HDL
computes `{4'd0, msb, shifted[14:7]}` so for v = 2^k, fast_log2(v) =
{4'd0, k, 8'd0} = k << 8. The v=0 case is the special branch returning 0.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

INPUT_A  = 0x000
INPUT_B  = 0x004
LOG_A    = 0x008
LOG_B    = 0x00C
MULTIPLY = 0x010
DIVIDE   = 0x014
SQRT_A   = 0x018
CONTROL  = 0x01C


def gen():
    tb = TortureBuilder("logos")
    tb.write(CONTROL, 1)  # reset

    # v = 0 → log2 returns 0 (special branch)
    tb.write(INPUT_A, 0)
    tb.read_assert(LOG_A, 0x0000)

    # v = 1 → msb=0, shifted = 1<<15 = 0x8000, frac = [14:7] of 0x8000 = 0x00
    # fast_log2 = {0000, msb=0, frac=0x00} = 0x0000
    tb.write(INPUT_A, 1)
    tb.read_assert(LOG_A, 0x0000)

    # v = 2 → msb=1, shifted = 2<<14 = 0x8000, frac=0, result = 0x0100
    tb.write(INPUT_A, 2)
    tb.read_assert(LOG_A, 0x0100)

    # v = 4 → msb=2, result = 0x0200
    tb.write(INPUT_A, 4)
    tb.read_assert(LOG_A, 0x0200)

    # v = 256 → msb=8, result = 0x0800
    tb.write(INPUT_A, 256)
    tb.read_assert(LOG_A, 0x0800)

    # v = 32768 → msb=15, result = 0x0F00
    tb.write(INPUT_A, 0x8000)
    tb.read_assert(LOG_A, 0x0F00)

    # INPUT_B values echo the same behavior on LOG_B
    tb.write(INPUT_B, 0)
    tb.read_assert(LOG_B, 0x0000)
    tb.write(INPUT_B, 16)  # msb=4
    tb.read_assert(LOG_B, 0x0400)

    # MULTIPLY/DIVIDE/SQRT depend on antilog fixed-point interpolation —
    # the approximation isn't exact so we don't assert exact values, just
    # exercise the path to catch crashes.
    tb.write(INPUT_A, 16)
    tb.write(INPUT_B, 16)
    tb.read_discard(MULTIPLY)
    tb.write(INPUT_A, 256)
    tb.write(INPUT_B, 16)
    tb.read_discard(DIVIDE)
    tb.write(INPUT_A, 256)
    tb.read_discard(SQRT_A)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"LOGOS torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("logos", firmware, mod_dir / "top.sv")
    ok, luts = build_module("logos", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("logos")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
