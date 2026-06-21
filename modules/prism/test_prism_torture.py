#!/usr/bin/env python3
"""Torture test for PRISM: PRISM: RGB to grayscale/luminance converter.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

RGB=0x000
LUMA=0x004
MIN_CH=0x008
MAX_CH=0x00C
SAT=0x010
INVERT=0x014

def gen():
    tb = TortureBuilder("prism")
    cases = [
        (0xFF0000, 255, 0, 0),
        (0x00FF00, 0, 255, 0),
        (0x0000FF, 0, 0, 255),
        (0xFFFFFF, 255, 255, 255),
        (0x000000, 0, 0, 0),
        (0x808080, 128, 128, 128),
        (0xFF8000, 255, 128, 0),
        (0x123456, 0x12, 0x34, 0x56),
    ]
    for rgb, r, g, b in cases:
        tb.write(RGB, rgb)
        luma = (r * 77 + g * 150 + b * 29) >> 8
        mn = min(r, g, b)
        mx = max(r, g, b)
        sat = mx - mn
        inv = ((255 - r) << 16) | ((255 - g) << 8) | (255 - b)
        tb.read_check(LUMA, luma & 0xFF)
        tb.read_check(MIN_CH, mn)
        tb.read_check(MAX_CH, mx)
        tb.read_check(SAT, sat)
        tb.read_check(INVERT, inv)
    tb.adversarial_write(RGB, 0xFFFFFFFF)
    tb.read_mix(LUMA, None)
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"PRISM torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("prism", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("prism", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("prism")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
