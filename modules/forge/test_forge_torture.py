#!/usr/bin/env python3
"""FORGE hash-based torture test.

Hashes multiple input words through the simplified SHA-256 compression,
verifies done status after each, reads all 4 output words. Uses multiple
distinct inputs and checks STATUS=done between rounds to differentiate
the hash from other modules.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

DATA    = 0x000
CONTROL = 0x004
STATUS  = 0x008
H0      = 0x00C
H1      = 0x010
H2      = 0x014
H3      = 0x018

def gen():
    tb = TortureBuilder("forge")

    # Hash "RIME" (0x52494D45)
    tb.write(DATA, 0x52494D45)
    tb.write(CONTROL, 1)
    tb.delay(100)
    tb.read_check(STATUS, 1)  # done
    tb.read_mix(H0, None)
    tb.read_mix(H1, None)
    tb.read_mix(H2, None)
    tb.read_mix(H3, None)

    # Hash 0x00000000
    tb.write(DATA, 0x00000000)
    tb.write(CONTROL, 1)
    tb.delay(100)
    tb.read_check(STATUS, 1)
    tb.read_mix(H0, None)
    tb.read_mix(H1, None)

    # Hash 0xFFFFFFFF
    tb.write(DATA, 0xFFFFFFFF)
    tb.write(CONTROL, 1)
    tb.delay(100)
    tb.read_check(STATUS, 1)
    tb.read_mix(H0, None)

    # Hash 0xDEADBEEF
    tb.write(DATA, 0xDEADBEEF)
    tb.write(CONTROL, 1)
    tb.delay(100)
    tb.read_check(STATUS, 1)
    tb.read_mix(H0, None)
    tb.read_mix(H1, None)
    tb.read_mix(H2, None)
    tb.read_mix(H3, None)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"FORGE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("forge", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("forge", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("forge")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
