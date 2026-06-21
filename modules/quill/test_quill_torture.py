#!/usr/bin/env python3
"""QUILL hash-based torture test.

Pushes/pops bytes across all 4 channels, verifies count, status, FIFO
ordering, clear behavior, and boundary conditions.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

TX_DATA = 0x000
CHANNEL = 0x004
STATUS  = 0x008
RX_DATA = 0x00C
COUNT   = 0x010
CONTROL = 0x014

def gen():
    tb = TortureBuilder("quill")

    # Clear all
    tb.write(CONTROL, 1)
    tb.write(CHANNEL, 0)
    tb.read_check(COUNT, 0)
    tb.read_check(STATUS, 0)

    # Push 3 bytes to channel 0, verify FIFO ordering
    tb.write(TX_DATA, 0xAA)
    tb.write(TX_DATA, 0xBB)
    tb.write(TX_DATA, 0xCC)
    tb.read_check(COUNT, 3)
    tb.read_check(RX_DATA, 0xAA)
    tb.read_check(RX_DATA, 0xBB)
    tb.read_check(COUNT, 1)
    tb.read_check(RX_DATA, 0xCC)
    tb.read_check(COUNT, 0)

    # Push to channel 1, verify isolation
    tb.write(CHANNEL, 1)
    tb.write(TX_DATA, 0x11)
    tb.write(TX_DATA, 0x22)
    tb.read_check(COUNT, 2)
    tb.write(CHANNEL, 0)
    tb.read_check(COUNT, 0)
    tb.write(CHANNEL, 1)
    tb.read_check(RX_DATA, 0x11)
    tb.read_check(RX_DATA, 0x22)

    # Fill channel 2 to capacity (8 bytes)
    tb.write(CHANNEL, 2)
    for i in range(8):
        tb.write(TX_DATA, i + 0x40)
    tb.read_check(COUNT, 8)
    for i in range(8):
        tb.read_check(RX_DATA, i + 0x40)
    tb.read_check(COUNT, 0)

    # Channel 3: push, clear all, verify empty
    tb.write(CHANNEL, 3)
    tb.write(TX_DATA, 0xFF)
    tb.write(TX_DATA, 0x00)
    tb.write(CONTROL, 1)
    tb.read_check(COUNT, 0)
    tb.read_check(STATUS, 0)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"QUILL torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("quill", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("quill", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("quill")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
