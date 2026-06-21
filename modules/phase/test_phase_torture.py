#!/usr/bin/env python3
"""Torture test for PHASE: PHASE: Periodic Hardware Accumulation and Signal Encoder — quadrature decoder with position counter

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

AB_INPUT  = 0x000
POSITION  = 0x004
DIRECTION = 0x008
EDGES     = 0x00C
CONTROL   = 0x010
STATUS    = 0x014

SAMPLE = 0x02
RESET  = 0x01


def step_ab(tb, a, b):
    tb.write(AB_INPUT, (b << 1) | a)
    tb.write(CONTROL, SAMPLE)


def gen():
    tb = TortureBuilder("phase")

    tb.write(CONTROL, RESET)
    tb.read_check(POSITION, 0)
    tb.read_check(EDGES, 0)

    # Forward sequence: 00 -> 01 -> 11 -> 10 -> 00 (4 steps = +4)
    step_ab(tb, 0, 0)
    step_ab(tb, 1, 0)
    step_ab(tb, 1, 1)
    step_ab(tb, 0, 1)
    step_ab(tb, 0, 0)
    tb.read_check(POSITION, 4)
    tb.read_check(EDGES, 4)

    # Reverse 2 steps: 00 -> 10 -> 11 (position = 4-2 = 2)
    step_ab(tb, 0, 1)
    step_ab(tb, 1, 1)
    tb.read_check(POSITION, 2)
    tb.read_check(DIRECTION, 2)

    # No movement (same state): position unchanged
    step_ab(tb, 1, 1)
    tb.read_check(POSITION, 2)
    tb.read_check(DIRECTION, 0)

    # Reset
    tb.write(CONTROL, RESET)
    tb.read_check(POSITION, 0)
    tb.read_check(EDGES, 0)


    tb.write(0x010, 1)
    tb.read_check(0x004, 0)
    tb.write(0x000, 0x01)
    tb.write(0x010, 2)
    tb.write(0x000, 0x03)
    tb.write(0x010, 2)
    tb.write(0x000, 0x02)
    tb.write(0x010, 2)
    tb.write(0x000, 0x00)
    tb.write(0x010, 2)
    tb.read_mix(0x004, None)
    tb.read_mix(0x00C, None)
    tb.write(0x000, 0x02)
    tb.write(0x010, 2)
    tb.write(0x000, 0x03)
    tb.write(0x010, 2)
    tb.write(0x000, 0x01)
    tb.write(0x010, 2)
    tb.write(0x000, 0x00)
    tb.write(0x010, 2)
    tb.read_mix(0x004, None)
    tb.adversarial_write(0x004, 0)
    tb.adversarial_write(0x00C, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"PHASE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("phase", firmware, mod_dir / "top.sv")
    ok, luts = build_module("phase", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("phase")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
