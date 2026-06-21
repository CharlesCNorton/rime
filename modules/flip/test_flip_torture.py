#!/usr/bin/env python3
"""FLIP (Fast Logical Interstitial Permutator) hash-based torture test.

Threads a running hash through 8x8 and 32x32 bit-matrix transpose operations:
identity, known patterns, round-trip, boundary values, adversarial inputs.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

# 8x8 registers
ROW8_BASE = 0x000   # 0x000-0x01C
COL8_BASE = 0x020   # 0x020-0x03C
STATUS    = 0x040

# 32x32 registers
ROW32_BASE = 0x100  # 0x100-0x17C
COL32_BASE = 0x200  # 0x200-0x27C


def transpose_8x8(rows):
    cols = [0] * 8
    for i in range(8):
        for j in range(8):
            if rows[i] & (1 << j):
                cols[j] |= (1 << i)
    return cols


def transpose_32x32(rows):
    cols = [0] * 32
    for i in range(32):
        for j in range(32):
            if rows[i] & (1 << j):
                cols[j] |= (1 << i)
    return [c & 0xFFFFFFFF for c in cols]


def gen():
    tb = TortureBuilder("flip")

    # --- 8x8: identity matrix ---
    identity = [1 << i for i in range(8)]
    for i, row in enumerate(identity):
        tb.write(ROW8_BASE + i * 4, row)
    # Transpose of identity is identity
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, identity[i])

    # --- 8x8: all ones ---
    for i in range(8):
        tb.write(ROW8_BASE + i * 4, 0xFF)
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, 0xFF)

    # --- 8x8: all zeros ---
    for i in range(8):
        tb.write(ROW8_BASE + i * 4, 0x00)
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, 0x00)

    # --- 8x8: known pattern (single bit in each row) ---
    rows = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80]
    expected = transpose_8x8(rows)
    for i, row in enumerate(rows):
        tb.write(ROW8_BASE + i * 4, row)
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, expected[i])

    # --- 8x8: checkerboard ---
    rows = [0xAA if i % 2 == 0 else 0x55 for i in range(8)]
    expected = transpose_8x8(rows)
    for i, row in enumerate(rows):
        tb.write(ROW8_BASE + i * 4, row)
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, expected[i])

    # --- 8x8: row 0 = 0xFF, rest = 0x00 ---
    rows = [0xFF] + [0x00] * 7
    expected = transpose_8x8(rows)
    for i, row in enumerate(rows):
        tb.write(ROW8_BASE + i * 4, row)
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, expected[i])

    # --- 8x8: double transpose = original ---
    rows = [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0]
    for i, row in enumerate(rows):
        tb.write(ROW8_BASE + i * 4, row)
    # Read transposed
    t1 = transpose_8x8(rows)
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, t1[i])
    # Write transposed back, read again — should get original
    for i in range(8):
        tb.write(ROW8_BASE + i * 4, t1[i])
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, rows[i])

    # --- 32x32: diagonal pattern (only set bit i in row i) ---
    rows32 = [1 << i for i in range(32)]
    exp32 = transpose_32x32(rows32)
    for i in range(32):
        tb.write(ROW32_BASE + i * 4, rows32[i])
    for i in [0, 7, 16, 31]:
        tb.read_check(COL32_BASE + i * 4, exp32[i])

    # --- Adversarial: write full 32-bit to 8x8 (only low 8 used) ---
    tb.adversarial_write(ROW8_BASE, 0xFFFFFFFF)
    for i in range(1, 8):
        tb.write(ROW8_BASE + i * 4, 0x00)
    # Only bit 0 of each column should be set (row 0 = 0xFF)
    for i in range(8):
        tb.read_check(COL8_BASE + i * 4, 0x01)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"FLIP torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("flip", firmware, mod_dir / "top.sv")
    ok, luts = build_module("flip", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("flip")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
