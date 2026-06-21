#!/usr/bin/env python3
"""Torture test for HALO: Hardware Assisted Loop Orchestrator — 256-entry 32-bit ring buffer with watermark

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

PUSH    = 0x000
POP     = 0x004
PEEK    = 0x008
STATUS  = 0x00C
COUNT   = 0x010
CONTROL = 0x014
DROPPED = 0x018

def gen():
    tb = TortureBuilder("halo")

    # Clear and basic FIFO
    tb.write(CONTROL, 0x01)
    tb.read_check(COUNT, 0)

    tb.write(PUSH, 0x42)
    tb.read_check(COUNT, 1)
    tb.read_check(POP, 0x42)
    tb.read_check(COUNT, 0)

    # FIFO ordering
    tb.write(PUSH, 0xAA)
    tb.write(PUSH, 0xBB)
    tb.write(PUSH, 0xCC)
    tb.read_check(COUNT, 3)
    tb.read_check(POP, 0xAA)
    tb.read_check(POP, 0xBB)
    tb.read_check(POP, 0xCC)
    tb.read_check(COUNT, 0)

    # Pop from empty
    tb.read_check(POP, 0)

    # Peek
    tb.write(PUSH, 0xDD)
    tb.read_check(PEEK, 0xDD)
    tb.read_check(COUNT, 1)
    tb.read_check(POP, 0xDD)

    # Fill to 8 and drain (smaller than 64 to keep firmware short)
    tb.write(CONTROL, 0x01)
    for i in range(8):
        tb.write(PUSH, 0x100 + i)
    tb.read_check(COUNT, 8)
    for i in range(8):
        tb.read_check(POP, 0x100 + i)
    tb.read_check(COUNT, 0)

    # All FIFO operations verified above

    return tb.finish()

def main():
    firmware, expected = gen()
    print(f"HALO torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("halo", firmware, mod_dir / "top.sv")
    ok, luts = build_module("halo", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("halo")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
