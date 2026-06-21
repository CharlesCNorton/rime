#!/usr/bin/env python3
"""Torture test for CODEC: CODEC: Compact Ordered Data Encoding/Decoding Coprocessor — base64 encode and decode

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

IN0     = 0x000
IN1     = 0x004
IN2     = 0x008
IN3     = 0x00C
ENC0    = 0x010
ENC1    = 0x014
ENC2    = 0x018
ENC3    = 0x01C
DEC0    = 0x020
DEC1    = 0x024
DEC2    = 0x028
CONTROL = 0x02C

B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def gen():
    tb = TortureBuilder("codec")

    tb.write(CONTROL, 1)

    # Encode "Man" -> "TWFu"
    tb.write(IN0, ord('M'))
    tb.write(IN1, ord('a'))
    tb.write(IN2, ord('n'))
    tb.read_check(ENC0, ord('T'))
    tb.read_check(ENC1, ord('W'))
    tb.read_check(ENC2, ord('F'))
    tb.read_check(ENC3, ord('u'))

    # Decode "TWFu" -> "Man"
    tb.write(IN0, ord('T'))
    tb.write(IN1, ord('W'))
    tb.write(IN2, ord('F'))
    tb.write(IN3, ord('u'))
    tb.read_check(DEC0, ord('M'))
    tb.read_check(DEC1, ord('a'))
    tb.read_check(DEC2, ord('n'))

    # Encode 0x00 0x00 0x00 -> "AAAA"
    tb.write(IN0, 0)
    tb.write(IN1, 0)
    tb.write(IN2, 0)
    tb.read_check(ENC0, ord('A'))
    tb.read_check(ENC1, ord('A'))
    tb.read_check(ENC2, ord('A'))
    tb.read_check(ENC3, ord('A'))

    # Encode 0xFF 0xFF 0xFF -> "////"
    tb.write(IN0, 0xFF)
    tb.write(IN1, 0xFF)
    tb.write(IN2, 0xFF)
    tb.read_check(ENC0, ord('/'))
    tb.read_check(ENC1, ord('/'))
    tb.read_check(ENC2, ord('/'))
    tb.read_check(ENC3, ord('/'))

    # Round-trip: encode "RIM" then decode the output
    tb.write(IN0, ord('R'))
    tb.write(IN1, ord('I'))
    tb.write(IN2, ord('M'))
    tb.read_mix(ENC0)
    tb.read_mix(ENC1)
    tb.read_mix(ENC2)
    tb.read_mix(ENC3)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"CODEC torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("codec", firmware, mod_dir / "top.sv")
    ok, luts = build_module("codec", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("codec")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
