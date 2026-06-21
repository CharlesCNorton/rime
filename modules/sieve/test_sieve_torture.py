#!/usr/bin/env python3
"""SIEVE hash-based torture test.

Threads a running hash through extract and deposit operations with
various positions, widths, boundary values, and adversarial inputs.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder, u32

SOURCE  = 0x000
CONFIG  = 0x004
EXTRACT = 0x008
TARGET  = 0x00C
FIELD   = 0x010
DEPOSIT = 0x014
MASK    = 0x018
CONTROL = 0x01C


def cfg(pos, width):
    return (width << 8) | pos


def sim_extract(source, pos, width):
    w = max(1, min(width, 32))
    mask = (1 << w) - 1 if w < 32 else 0xFFFFFFFF
    return (source >> pos) & mask


def sim_deposit(target, field, pos, width):
    w = max(1, min(width, 32))
    mask_raw = (1 << w) - 1 if w < 32 else 0xFFFFFFFF
    mask_pos = (mask_raw << pos) & 0xFFFFFFFF
    return u32((target & ~mask_pos) | ((field << pos) & mask_pos))


def sim_mask(pos, width):
    w = max(1, min(width, 32))
    mask_raw = (1 << w) - 1 if w < 32 else 0xFFFFFFFF
    return (mask_raw << pos) & 0xFFFFFFFF


def gen():
    tb = TortureBuilder("sieve")

    tb.reset(CONTROL, bit=0)

    # --- Extract low byte: pos=0, width=8 ---
    tb.write(SOURCE, 0xDEADBEEF)
    tb.write(CONFIG, cfg(0, 8))
    tb.read_check(EXTRACT, sim_extract(0xDEADBEEF, 0, 8))
    tb.read_check(MASK, sim_mask(0, 8))

    # --- Extract bits [19:4]: pos=4, width=16 ---
    tb.write(CONFIG, cfg(4, 16))
    tb.read_check(EXTRACT, sim_extract(0xDEADBEEF, 4, 16))

    # --- Extract full word: pos=0, width=32 ---
    tb.write(CONFIG, cfg(0, 32))
    tb.read_check(EXTRACT, sim_extract(0xDEADBEEF, 0, 32))

    # --- Extract single bit: pos=31, width=1 ---
    tb.write(CONFIG, cfg(31, 1))
    tb.read_check(EXTRACT, sim_extract(0xDEADBEEF, 31, 1))

    # --- Extract high nibble: pos=28, width=4 ---
    tb.write(CONFIG, cfg(28, 4))
    tb.read_check(EXTRACT, sim_extract(0xDEADBEEF, 28, 4))

    # --- Deposit: insert 0xAB at pos=8, width=8 into 0x12345678 ---
    tb.write(SOURCE, 0)
    tb.write(CONFIG, cfg(8, 8))
    tb.write(TARGET, 0x12345678)
    tb.write(FIELD, 0xAB)
    tb.read_check(DEPOSIT, sim_deposit(0x12345678, 0xAB, 8, 8))

    # --- Deposit: set bits [31:16] to 0xBEEF ---
    tb.write(CONFIG, cfg(16, 16))
    tb.write(TARGET, 0x00001234)
    tb.write(FIELD, 0xBEEF)
    tb.read_check(DEPOSIT, sim_deposit(0x00001234, 0xBEEF, 16, 16))

    # --- Deposit: single bit at pos=0 ---
    tb.write(CONFIG, cfg(0, 1))
    tb.write(TARGET, 0xFFFFFFFE)
    tb.write(FIELD, 1)
    tb.read_check(DEPOSIT, sim_deposit(0xFFFFFFFE, 1, 0, 1))

    # --- Adversarial: width=0 (should clamp to 1) ---
    tb.write(SOURCE, 0xFFFFFFFF)
    tb.write(CONFIG, cfg(0, 0))
    tb.read_check(EXTRACT, sim_extract(0xFFFFFFFF, 0, 1))

    # --- Reset and verify ---
    tb.reset(CONTROL, bit=0)
    tb.read_check(EXTRACT, sim_extract(0, 0, 1))

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"SIEVE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("sieve", firmware, mod_dir / "top.sv")
    ok, luts = build_module("sieve", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("sieve")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
