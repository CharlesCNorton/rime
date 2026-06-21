#!/usr/bin/env python3
"""Torture test for RANK: RANK: Rapid Associative Numerical Keyed sorter — 8-element parallel sorting network

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

INPUT   = 0x000
OUTPUT  = 0x020
CONTROL = 0x040
STATUS  = 0x044


def gen():
    tb = TortureBuilder("rank")
    tb.write(CONTROL, 0x02)  # reset

    # Sort [8,3,7,1,5,2,6,4] -> [1,2,3,4,5,6,7,8]
    vals = [8, 3, 7, 1, 5, 2, 6, 4]
    for i, v in enumerate(vals):
        tb.write(INPUT + i * 4, v)
    tb.write(CONTROL, 0x01)
    tb.read_check(STATUS, 1)
    expected = sorted(vals)
    for i, v in enumerate(expected):
        tb.read_check(OUTPUT + i * 4, v)

    # Already sorted
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(INPUT + i * 4, i + 1)
    tb.write(CONTROL, 0x01)
    for i in range(8):
        tb.read_check(OUTPUT + i * 4, i + 1)

    # Reverse sorted
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(INPUT + i * 4, 8 - i)
    tb.write(CONTROL, 0x01)
    for i in range(8):
        tb.read_check(OUTPUT + i * 4, i + 1)

    # All identical
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(INPUT + i * 4, 42)
    tb.write(CONTROL, 0x01)
    for i in range(8):
        tb.read_check(OUTPUT + i * 4, 42)

    # Boundary values
    tb.write(CONTROL, 0x02)
    extreme = [0, 0xFFFFFFFF, 1, 0xFFFFFFFE, 0x80000000, 0x7FFFFFFF, 0, 0xFFFFFFFF]
    for i, v in enumerate(extreme):
        tb.write(INPUT + i * 4, v)
    tb.write(CONTROL, 0x01)
    for i, v in enumerate(sorted(extreme)):
        tb.read_check(OUTPUT + i * 4, v)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"RANK torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("rank", firmware, mod_dir / "top.sv")
    ok, luts = build_module("rank", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("rank")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
