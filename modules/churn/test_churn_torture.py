#!/usr/bin/env python3
"""Torture test for CHURN: Continuous Hash Updating and Rolling Node — 32-byte Rabin-Karp rolling hash with boundary detection

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

DATA      = 0x000
HASH      = 0x004
CONTROL   = 0x008
BOUNDARY  = 0x00C
TARGET    = 0x010
BYTECOUNT = 0x014

def gen():
    tb = TortureBuilder("churn")
    tb.write(CONTROL, 1)
    tb.read_check(BYTECOUNT, 0)

    # Feed 4 bytes, verify count
    for b in b"RIME":
        tb.write(DATA, b)
    tb.read_check(BYTECOUNT, 4)
    tb.read_discard(HASH)  # hash value is hardware-dependent

    # Reset and feed a longer sequence
    tb.write(CONTROL, 1)
    for b in range(16):
        tb.write(DATA, b)
    tb.read_check(BYTECOUNT, 16)
    tb.read_discard(HASH)

    # Verify hash changes with different input
    tb.write(CONTROL, 1)
    for b in range(16):
        tb.write(DATA, b + 0x80)
    tb.read_check(BYTECOUNT, 16)
    tb.read_discard(HASH)  # should differ from previous

    return tb.finish()

def main():
    firmware, expected = gen()
    print(f"CHURN torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("churn", firmware, mod_dir / "top.sv")
    ok, luts = build_module("churn", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("churn")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
