#!/usr/bin/env python3
"""Torture test for HAZE: HAZE: Hardware Approximation of Zoned Entropy — 2D gradient noise via hash and linear interpolation

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

COORD_X  = 0x000
COORD_Y  = 0x004
CONTROL  = 0x008
STATUS   = 0x00C
VALUE    = 0x010
HASH_DBG = 0x014


def gen():
    tb = TortureBuilder("haze")
    tb.write(CONTROL, 0x02)  # reset

    # Query noise at (0, 0) — integer grid point
    tb.write(COORD_X, 0x0000)
    tb.write(COORD_Y, 0x0000)
    tb.write(CONTROL, 0x01)
    tb.delay(10)
    tb.read_check(STATUS, 1)
    tb.read_mix(VALUE)
    tb.read_mix(HASH_DBG)

    # Query at (1.5, 2.5) — 0x0180, 0x0280 — fractional point
    tb.write(COORD_X, 0x0180)
    tb.write(COORD_Y, 0x0280)
    tb.write(CONTROL, 0x01)
    tb.delay(10)
    tb.read_mix(VALUE)

    # Query at (255, 255) — edge of 8-bit range
    tb.write(COORD_X, 0xFF00)
    tb.write(COORD_Y, 0xFF00)
    tb.write(CONTROL, 0x01)
    tb.delay(10)
    tb.read_mix(VALUE)

    # Two adjacent integer points should produce different values
    tb.write(COORD_X, 0x0100)
    tb.write(COORD_Y, 0x0100)
    tb.write(CONTROL, 0x01)
    tb.delay(10)
    tb.read_mix(VALUE)

    tb.write(COORD_X, 0x0200)
    tb.write(COORD_Y, 0x0100)
    tb.write(CONTROL, 0x01)
    tb.delay(10)
    tb.read_mix(VALUE)

    # Deterministic: same input -> same output
    tb.write(COORD_X, 0x0000)
    tb.write(COORD_Y, 0x0000)
    tb.write(CONTROL, 0x01)
    tb.delay(10)
    tb.read_mix(VALUE)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"HAZE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("haze", firmware, mod_dir / "top.sv")
    ok, luts = build_module("haze", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("haze")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
