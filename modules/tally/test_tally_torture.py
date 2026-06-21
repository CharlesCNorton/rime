#!/usr/bin/env python3
"""TALLY hash-based torture test.

Threads a running hash through multiply-accumulate operations on all 4
channels: basic MAC, accumulation across multiple operations, zero
operands, boundary values, channel independence, reset.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder, u32

OP_A    = 0x000
OP_B    = 0x004
ACC0    = 0x008
ACC1    = 0x00C
ACC2    = 0x010
ACC3    = 0x014
STATUS  = 0x018
CONTROL = 0x01C


def op_a_val(a16, channel):
    return (channel << 16) | (a16 & 0xFFFF)


def gen():
    tb = TortureBuilder("tally")

    tb.reset(CONTROL, bit=0)

    # --- Channel 0: 10 * 20 = 200 ---
    tb.write(OP_A, op_a_val(10, 0))
    tb.write(OP_B, 20)
    tb.delay(25)
    tb.read_check(STATUS, 0x01)
    tb.read_check(ACC0, 200)

    # --- Channel 0: accumulate 10*20 + 30*40 = 200 + 1200 = 1400 ---
    tb.write(OP_A, op_a_val(30, 0))
    tb.write(OP_B, 40)
    tb.delay(25)
    tb.read_check(ACC0, 1400)

    # --- Channel 1: 100 * 100 = 10000 ---
    tb.write(OP_A, op_a_val(100, 1))
    tb.write(OP_B, 100)
    tb.delay(25)
    tb.read_check(ACC1, 10000)

    # --- Channel independence: ACC0 still 1400 ---
    tb.read_check(ACC0, 1400)

    # --- Channel 2: multiply by 0 ---
    tb.write(OP_A, op_a_val(0xFFFF, 2))
    tb.write(OP_B, 0)
    tb.delay(25)
    tb.read_check(ACC2, 0)

    # --- Channel 3: 0 * N = 0 ---
    tb.write(OP_A, op_a_val(0, 3))
    tb.write(OP_B, 0xFFFF)
    tb.delay(25)
    tb.read_check(ACC3, 0)

    # --- Max * Max: 0xFFFF * 0xFFFF = 0xFFFE0001 ---
    tb.write(OP_A, op_a_val(0xFFFF, 2))
    tb.write(OP_B, 0xFFFF)
    tb.delay(25)
    tb.read_check(ACC2, u32(0xFFFF * 0xFFFF))

    # --- Accumulator overflow: add max again ---
    tb.write(OP_A, op_a_val(0xFFFF, 2))
    tb.write(OP_B, 0xFFFF)
    tb.delay(25)
    expected_overflow = u32(0xFFFF * 0xFFFF + 0xFFFF * 0xFFFF)
    tb.read_check(ACC2, expected_overflow)

    # --- 1 * 1 on channel 3 ---
    tb.write(OP_A, op_a_val(1, 3))
    tb.write(OP_B, 1)
    tb.delay(25)
    tb.read_check(ACC3, 1)

    # --- Reset and verify all channels clear ---
    tb.reset(CONTROL, bit=0)
    tb.read_check(ACC0, 0)
    tb.read_check(ACC1, 0)
    tb.read_check(ACC2, 0)
    tb.read_check(ACC3, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"TALLY torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("tally", firmware, mod_dir / "top.sv")
    ok, luts = build_module("tally", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("tally")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
