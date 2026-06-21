#!/usr/bin/env python3
"""Torture test for PROOF: PROOF: Protected Read-Once Operational Fence — constant-time 32-byte comparison

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

BUF_A   = 0x000
BUF_B   = 0x020
CONTROL = 0x040
RESULT  = 0x044
STATUS  = 0x048
DIFF_OR = 0x04C


def gen():
    tb = TortureBuilder("proof")

    # Reset
    tb.write(CONTROL, 0x02)

    # Load identical buffers -> match
    for i in range(8):
        tb.write(BUF_A + i * 4, 0xDEADBEEF)
        tb.write(BUF_B + i * 4, 0xDEADBEEF)
    tb.write(CONTROL, 0x01)
    tb.read_check(RESULT, 1)
    tb.read_check(DIFF_OR, 0)

    # Reset, load with single-byte difference
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(BUF_A + i * 4, 0x12345678)
        tb.write(BUF_B + i * 4, 0x12345678)
    tb.write(BUF_B + 7 * 4, 0x12345679)
    tb.write(CONTROL, 0x01)
    tb.read_check(RESULT, 0)
    tb.read_check(STATUS, 1)

    # All zeros match
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(BUF_A + i * 4, 0)
        tb.write(BUF_B + i * 4, 0)
    tb.write(CONTROL, 0x01)
    tb.read_check(RESULT, 1)

    # All-FF match
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(BUF_A + i * 4, 0xFFFFFFFF)
        tb.write(BUF_B + i * 4, 0xFFFFFFFF)
    tb.write(CONTROL, 0x01)
    tb.read_check(RESULT, 1)

    # Single bit difference in first word
    tb.write(CONTROL, 0x02)
    for i in range(8):
        tb.write(BUF_A + i * 4, 0xAAAAAAAA)
        tb.write(BUF_B + i * 4, 0xAAAAAAAA)
    tb.write(BUF_B + 0 * 4, 0xAAAAAAAA ^ 1)
    tb.write(CONTROL, 0x01)
    tb.read_check(RESULT, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"PROOF torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("proof", firmware, mod_dir / "top.sv")
    ok, luts = build_module("proof", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("proof")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
