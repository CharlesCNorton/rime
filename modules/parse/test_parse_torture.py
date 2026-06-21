#!/usr/bin/env python3
"""PARSE hash-based torture test.

Configures a 3-state NFA (S0 -'A'-> S1 -'B'-> S2[accept]), feeds matching
and non-matching byte sequences, verifies match count and status.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

INPUT   = 0x000
STATUS  = 0x004
CONTROL = 0x008
MATCHES = 0x00C
STATE0  = 0x100
STATE1  = 0x104
STATE2  = 0x108

def gen():
    tb = TortureBuilder("parse")

    # Reset NFA
    tb.reset(CONTROL, bit=0)
    tb.read_check(MATCHES, 0)

    # Configure: S0 matches 'A' -> S1, else stay S0
    # bits[7:0]=match_byte, bits[10:8]=next_match, bits[13:11]=next_nomatch, bit14=accept, bit15=active_on_reset
    tb.write(STATE0, ord('A') | (1 << 8) | (0 << 11) | (1 << 15))  # S0: match 'A'->S1, no-match->S0, active on reset
    tb.write(STATE1, ord('B') | (2 << 8) | (0 << 11))               # S1: match 'B'->S2, no-match->S0
    tb.write(STATE2, 0xFF | (0 << 8) | (7 << 11) | (1 << 14))       # S2: accept, match anything->S0, no-match->stay

    tb.reset(CONTROL, bit=0)

    # Feed "AB" -> should match
    tb.write(INPUT, ord('A'))
    tb.write(INPUT, ord('B'))
    tb.read_check(MATCHES, 1)

    # Feed "AB" again
    tb.write(INPUT, ord('A'))
    tb.write(INPUT, ord('B'))
    tb.read_check(MATCHES, 2)

    # Feed "AX" -> no match (X doesn't match 'B')
    tb.write(INPUT, ord('A'))
    tb.write(INPUT, ord('X'))
    tb.read_check(MATCHES, 2)  # still 2

    # Feed "AB" once more
    tb.write(INPUT, ord('A'))
    tb.write(INPUT, ord('B'))
    tb.read_check(MATCHES, 3)

    # Reset and verify count clears
    tb.reset(CONTROL, bit=0)
    tb.read_check(MATCHES, 0)

    # Adversarial: boundary bytes
    tb.adversarial_write(INPUT, 0xFF)
    tb.adversarial_write(INPUT, 0x00)
    tb.read_check(MATCHES, 0)


    tb.write(0x008, 1)
    tb.write(0x100, (1 << 15) | (7 << 11) | (1 << 8) | ord('A'))
    tb.write(0x104, (0 << 15) | (7 << 11) | (2 << 8) | ord('B'))
    tb.write(0x108, (1 << 14) | (7 << 11) | (7 << 8) | 0x00)
    tb.write(0x008, 1)
    tb.write(0x000, ord('A'))
    tb.write(0x000, ord('B'))
    tb.read_mix(0x004, None)
    tb.read_mix(0x00C, None)
    for ch in [ord('X'), ord('Y'), ord('Z')]:
        tb.write(0x000, ch)
    tb.read_mix(0x004, None)
    tb.adversarial_write(0x004, 0)
    tb.adversarial_write(0x00C, 0)
    tb.write(0x008, 1)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"PARSE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("parse", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("parse", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("parse")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
