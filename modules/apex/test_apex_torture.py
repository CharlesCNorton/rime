#!/usr/bin/env python3
"""APEX (Asynchronous Priority Evaluation matriX) hash-based torture test.

Threads a running hash through priority queue operations: push, pop order
verification, peek, clear, min/max mode switch.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

PUSH_VAL = 0x000
PUSH_PRI = 0x004
POP_VAL  = 0x008
PEEK_VAL = 0x00C
PEEK_PRI = 0x010
COUNT    = 0x014
CONTROL  = 0x018
STATUS   = 0x01C


def gen():
    tb = TortureBuilder("apex")

    # --- Clear and verify empty ---
    tb.write(CONTROL, 0x01)
    tb.read_check(COUNT, 0)
    tb.read_check(STATUS, 0x01)  # empty=1, full=0, min_mode=0

    # --- Push 3 entries with distinct priorities (max-first) ---
    tb.write(PUSH_VAL, 0xAABBCCDD)
    tb.write(PUSH_PRI, 10)
    tb.write(PUSH_VAL, 0x11223344)
    tb.write(PUSH_PRI, 50)
    tb.write(PUSH_VAL, 0x55667788)
    tb.write(PUSH_PRI, 30)
    tb.read_check(COUNT, 3)

    # Peek: highest priority is 50
    tb.read_check(PEEK_VAL, 0x11223344)
    tb.read_check(PEEK_PRI, 50)

    # Pop: descending order 50, 30, 10
    tb.read_check(POP_VAL, 0x11223344)
    tb.read_check(POP_VAL, 0x55667788)
    tb.read_check(POP_VAL, 0xAABBCCDD)
    tb.read_check(COUNT, 0)

    # Pop from empty
    tb.read_check(POP_VAL, 0)

    # --- Min mode: push 3, pop in ascending order ---
    tb.write(CONTROL, 0x03)  # clear + min_mode
    tb.write(PUSH_VAL, 0x000000C8)
    tb.write(PUSH_PRI, 100)
    tb.write(PUSH_VAL, 0x00000005)
    tb.write(PUSH_PRI, 5)
    tb.write(PUSH_VAL, 0x00000032)
    tb.write(PUSH_PRI, 50)

    tb.read_check(PEEK_VAL, 0x00000005)
    tb.read_check(PEEK_PRI, 5)
    tb.read_check(POP_VAL, 0x00000005)
    tb.read_check(POP_VAL, 0x00000032)
    tb.read_check(POP_VAL, 0x000000C8)
    tb.read_check(COUNT, 0)

    # --- Back to max mode, push ascending priorities ---
    tb.write(CONTROL, 0x01)  # clear, max mode
    for i in range(8):
        tb.write(PUSH_VAL, i)
        tb.write(PUSH_PRI, i)
    tb.read_check(COUNT, 8)
    # Pop: should come out 7, 6, 5, ..., 0
    for i in range(7, -1, -1):
        tb.read_check(POP_VAL, i)
    tb.read_check(COUNT, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"APEX torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("apex", firmware, mod_dir / "top.sv")
    ok, luts = build_module("apex", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("apex")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
