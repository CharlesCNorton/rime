#!/usr/bin/env python3
"""Torture test for CELL: CELL: Configurable Elementary Local Logic automaton — 64-cell 1D cellular automaton with Wolfram rule byte

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

STATE_LO = 0x000
STATE_HI = 0x004
RULE     = 0x008
CONTROL  = 0x00C
GEN      = 0x010
ALIVE    = 0x014

STEP  = 0x01
RESET = 0x02


def wolfram_step(state_64, rule_byte):
    result = 0
    for i in range(64):
        left   = (state_64 >> ((i + 63) % 64)) & 1
        center = (state_64 >> i) & 1
        right  = (state_64 >> ((i + 1) % 64)) & 1
        neighborhood = (left << 2) | (center << 1) | right
        result |= ((rule_byte >> neighborhood) & 1) << i
    return result


def gen():
    tb = TortureBuilder("cell")

    tb.write(CONTROL, RESET)
    tb.read_check(GEN, 0)

    # Rule 30, single cell in center (bit 32)
    tb.write(RULE, 30)
    tb.write(STATE_LO, 0)
    tb.write(STATE_HI, 1)  # bit 32 = 1
    initial = 1 << 32

    # Step once
    tb.write(CONTROL, STEP)
    expected = wolfram_step(initial, 30)
    tb.read_check(STATE_LO, expected & 0xFFFFFFFF)
    tb.read_check(STATE_HI, (expected >> 32) & 0xFFFFFFFF)
    tb.read_check(GEN, 1)

    # Step again
    tb.write(CONTROL, STEP)
    expected2 = wolfram_step(expected, 30)
    tb.read_check(STATE_LO, expected2 & 0xFFFFFFFF)
    tb.read_check(STATE_HI, (expected2 >> 32) & 0xFFFFFFFF)
    tb.read_check(GEN, 2)

    # Rule 110 (Turing-complete)
    tb.write(CONTROL, RESET)
    tb.write(RULE, 110)
    tb.write(STATE_LO, 0xAAAAAAAA)
    tb.write(STATE_HI, 0x55555555)
    state110 = (0x55555555 << 32) | 0xAAAAAAAA
    tb.write(CONTROL, STEP)
    exp110 = wolfram_step(state110, 110)
    tb.read_check(STATE_LO, exp110 & 0xFFFFFFFF)
    tb.read_check(STATE_HI, (exp110 >> 32) & 0xFFFFFFFF)

    # Alive count
    tb.read_check(ALIVE, bin(exp110).count('1'))

    # Rule 0: all cells die
    tb.write(RULE, 0)
    tb.write(STATE_LO, 0xFFFFFFFF)
    tb.write(STATE_HI, 0xFFFFFFFF)
    tb.write(CONTROL, STEP)
    tb.read_check(STATE_LO, 0)
    tb.read_check(STATE_HI, 0)
    tb.read_check(ALIVE, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"CELL torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("cell", firmware, mod_dir / "top.sv")
    ok, luts = build_module("cell", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("cell")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
