#!/usr/bin/env python3
"""VIGIL hash-based torture test.

Exercises all Hamming(7,4) operations: encode all 16 values, decode
clean codewords, inject single-bit errors and verify correction,
read syndrome and error counter.

Adversarial: decode invalid 7-bit patterns, double-bit errors
(uncorrectable), rapid encode-decode without reads between.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

ENCODE    = 0x000
CODED     = 0x004
DECODE    = 0x008
DATA      = 0x00C
SYNDROME  = 0x010
CORRECTED = 0x014
CTRL      = 0x018
ERRORS    = 0x01C


def hamming_encode(d):
    """Reference Hamming(7,4) encoder matching vigil.sv bit layout.

    Position: 1    2    3    4    5    6    7
    Content:  p1   p2   d1   p3   d2   d3   d4
    Index:    [0]  [1]  [2]  [3]  [4]  [5]  [6]

    Input d[3:0] = {d4, d3, d2, d1} where d1=bit0, d2=bit1, d3=bit2, d4=bit3.
    """
    d1, d2, d3, d4 = d & 1, (d >> 1) & 1, (d >> 2) & 1, (d >> 3) & 1
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p3 = d2 ^ d3 ^ d4
    return p1 | (p2 << 1) | (d1 << 2) | (p3 << 3) | (d2 << 4) | (d3 << 5) | (d4 << 6)


def gen():
    tb = TortureBuilder("vigil")
    tb.reset(CTRL, bit=0)

    # Encode all 16 values and verify
    for d in range(16):
        expected_code = hamming_encode(d)
        tb.write(ENCODE, d)
        tb.read_check(CODED, expected_code)

    # Decode all 16 clean codewords
    for d in range(16):
        code = hamming_encode(d)
        tb.write(DECODE, code)
        tb.read_check(DATA, d)
        tb.read_check(SYNDROME, 0)
        tb.read_check(CORRECTED, 0)

    # Inject single-bit errors on each of 7 positions for data=5
    d = 5
    code = hamming_encode(d)
    for bit in range(7):
        corrupted = code ^ (1 << bit)
        tb.write(DECODE, corrupted)
        tb.read_check(DATA, d)
        tb.read_check(SYNDROME, bit + 1)
        tb.read_check(CORRECTED, 1)

    # Error counter should be 7
    tb.read_check(ERRORS, 7)

    # Reset error counter
    tb.reset(CTRL, bit=0)
    tb.read_check(ERRORS, 0)

    # Adversarial: decode 0x7F (all bits set) — d=15, no error
    tb.write(DECODE, 0x7F)
    tb.read_check(DATA, 15)
    tb.read_check(SYNDROME, 0)
    tb.read_check(CORRECTED, 0)

    # Adversarial: decode 0x00 — d=0, no error
    tb.write(DECODE, 0x00)
    tb.read_check(DATA, 0)
    tb.read_check(SYNDROME, 0)

    # Adversarial: encode then immediately decode without reading between
    for d in range(16):
        tb.write(ENCODE, d)
        tb.write(DECODE, hamming_encode(d))
    tb.read_check(DATA, 15)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"VIGIL torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("vigil", firmware, mod_dir / "top.sv")
    ok, luts = build_module("vigil", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("vigil")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
