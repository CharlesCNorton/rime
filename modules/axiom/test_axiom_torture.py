#!/usr/bin/env python3
"""Torture test for AXIOM: AXIOM: hardware JSON/structured data token scanner.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("axiom")
    tb.reset(0x00C, bit=0)
    tb.read_check(0x008, 0)
    tb.read_check(0x014, 0)
    tb.write(0x000, ord("{"))
    tb.read_check(0x008, 1)
    tb.write(0x000, ord("}"))
    tb.read_check(0x008, 0)
    tb.write(0x000, ord("["))
    tb.write(0x000, ord("["))
    tb.read_check(0x008, 2)
    tb.write(0x000, ord("]"))
    tb.write(0x000, ord("]"))
    tb.read_check(0x008, 0)
    tb.adversarial_write(0x000, 0xFF)
    tb.read_mix(0x014, None)
    tb.reset(0x00C, bit=0)
    tb.read_check(0x008, 0)

    tb.write(0x00C, 1)
    tb.read_check(0x010, 0)
    for ch in [0x7B, 0x22, 0x6B, 0x65, 0x79, 0x22, 0x3A, 0x34, 0x32, 0x7D]:
        tb.write(0x000, ch)
    tb.read_mix(0x004, None)
    tb.read_mix(0x008, None)
    tb.read_check(0x010, 10)
    tb.read_mix(0x014, None)
    tb.adversarial_write(0x004, 0)
    tb.adversarial_write(0x008, 0)
    tb.adversarial_write(0x010, 0)
    tb.write(0x00C, 1)
    for ch in [0x5B, 0x5B, 0x5B]:
        tb.write(0x000, ch)
    tb.read_check(0x008, 3)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"AXIOM torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("axiom", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("axiom", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("axiom")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
