#!/usr/bin/env python3
"""Torture test for HEDGE: HEDGE: hardware token bucket rate limiter.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

REQ=0x000
RESULT=0x004
CTRL=0x008
RATE=0x00C
BURST=0x010
TOKENS=0x014
ALLOWED=0x018
DENIED=0x01C

def gen():
    tb = TortureBuilder("hedge")
    tb.write(CTRL, 3)
    tb.write(RATE, 0)
    tb.write(BURST, 5)
    tb.read_check(TOKENS, 0)
    tb.read_check(ALLOWED, 0)
    tb.read_check(DENIED, 0)
    tb.write(REQ, 1)
    tb.read_check(RESULT, 0)
    tb.read_check(DENIED, 1)
    tb.write(RATE, 255)
    tb.delay(100)
    tb.read_mix(TOKENS, None)
    tb.write(REQ, 1)
    tb.read_check(RESULT, 1)
    tb.read_check(ALLOWED, 1)
    for _ in range(10):
        tb.write(REQ, 1)
    tb.read_mix(ALLOWED, None)
    tb.read_mix(DENIED, None)
    tb.adversarial_write(RATE, 0xFFFFFFFF)
    tb.adversarial_write(BURST, 0xFFFFFFFF)
    tb.write(CTRL, 3)
    tb.read_check(TOKENS, 0)
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"HEDGE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("hedge", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("hedge", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("hedge")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
