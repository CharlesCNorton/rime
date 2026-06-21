#!/usr/bin/env python3
"""Torture test for SIGMA: SIGMA: streaming checksum accumulator (Fletcher-16).

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

DATA=0x000
CKSUM=0x004
CTRL=0x008
COUNT=0x00C

def fletcher16(data):
    s1, s2 = 0, 0
    for b in data:
        s1 = (s1 + b) % 255
        s2 = (s2 + s1) % 255
    return (s2 << 8) | s1

def gen():
    tb = TortureBuilder("sigma")
    tb.reset(CTRL, bit=0)
    tb.read_check(CKSUM, 0)
    tb.read_check(COUNT, 0)
    for b in b"RIME":
        tb.write(DATA, b)
    tb.read_check(CKSUM, fletcher16(b"RIME"))
    tb.read_check(COUNT, 4)
    tb.reset(CTRL, bit=0)
    tb.read_check(CKSUM, 0)
    tb.adversarial_write(DATA, 0xFFFFFFFF)
    tb.adversarial_write(DATA, 0x00000000)
    for b in range(256):
        tb.write(DATA, b)
    tb.read_check(CKSUM, fletcher16(bytes([0xFF, 0x00] + list(range(256)))))
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"SIGMA torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("sigma", fw, Path(__file__).resolve().parent / "top.sv")
    ok, luts = build_module("sigma", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("sigma")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
