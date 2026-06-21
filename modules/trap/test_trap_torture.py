#!/usr/bin/env python3
"""Torture test for TRAP: TRAP: Triggered Response to Address Predicate — 4-address hardware breakpoint/watchpoint unit

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

MATCH0  = 0x000
MATCH1  = 0x004
ENABLE  = 0x010
FLAGS   = 0x014
LAST    = 0x018
COUNT   = 0x01C
CONTROL = 0x020


def gen():
    tb = TortureBuilder("trap")

    tb.write(CONTROL, 1)  # reset

    # Set match address 0 and enable it
    tb.write(MATCH0, 0x12345678)
    tb.write(ENABLE, 0x01)

    # No match yet
    tb.read_check(FLAGS, 0)
    tb.read_check(COUNT, 0)

    # Match happens passively via snoop — in a standalone torture test
    # without the CPU bus, we just verify register read/write and reset.
    tb.write(MATCH1, 0xDEADBEEF)
    tb.write(ENABLE, 0x03)
    tb.read_check(ENABLE, 0x03)  # verify enable reads back as written
    tb.read_mix(FLAGS)
    tb.read_mix(COUNT)

    # Reset
    tb.write(CONTROL, 1)
    tb.read_check(COUNT, 0)


    tb.write(0x020, 1)
    tb.write(0x000, 0x30000000)
    tb.write(0x004, 0x31000000)
    tb.write(0x008, 0x00000000)
    tb.write(0x00C, 0xFFFFFFFF)
    tb.write(0x010, 0x0F)
    tb.delay(10)
    tb.read_mix(0x014, None)
    tb.read_mix(0x018, None)
    tb.read_mix(0x01C, None)
    tb.adversarial_write(0x014, 0)
    tb.adversarial_write(0x018, 0)
    tb.write(0x020, 1)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"TRAP torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("trap", firmware, mod_dir / "top.sv")
    ok, luts = build_module("trap", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("trap")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
