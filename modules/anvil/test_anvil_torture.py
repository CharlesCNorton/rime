#!/usr/bin/env python3
"""ANVIL hash-based torture test.

Threads a running hash through every ANVIL operation: reset, feed bytes,
read CRC, read count, boundary values, rapid re-reset.  If any register
returns wrong data, the hash diverges.

Adversarial: feed 0xFF, 0x00, 0xFFFFFFFF (only low byte used), read
after reset (should be 0), double-reset, read raw vs inverted.
"""
import sys
import zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder, u32

DATA   = 0x000
CRC    = 0x004
CTRL   = 0x008
RAW    = 0x00C
COUNT  = 0x010


def gen():
    tb = TortureBuilder("anvil")

    # Reset
    tb.reset(CTRL, bit=0)

    # After reset: CRC should be 0x00000000 (inverted 0xFFFFFFFF)
    # Actually the CRC register returns the finalized value.
    # CRC-32 of empty = 0x00000000
    tb.read_check(CRC, 0x00000000)
    tb.read_check(COUNT, 0)

    # Feed "RIME" one byte at a time
    for b in b"RIME":
        tb.write(DATA, b)
    expected_crc = zlib.crc32(b"RIME") & 0xFFFFFFFF
    tb.read_check(CRC, expected_crc)
    tb.read_check(COUNT, 4)

    # Read RAW (non-inverted state) — just mix it, value is implementation-dependent
    tb.read_mix(RAW, u32(~expected_crc))

    # Reset and verify clean
    tb.reset(CTRL, bit=0)
    tb.read_check(CRC, 0x00000000)
    tb.read_check(COUNT, 0)

    # Adversarial: feed boundary values
    tb.adversarial_write(DATA, 0x00)
    tb.adversarial_write(DATA, 0xFF)
    tb.adversarial_write(DATA, 0xFFFFFFFF)  # only low byte should matter = 0xFF
    expected_crc2 = zlib.crc32(bytes([0x00, 0xFF, 0xFF])) & 0xFFFFFFFF
    tb.read_check(CRC, expected_crc2)
    tb.read_check(COUNT, 3)

    # Adversarial: double-reset
    tb.reset(CTRL, bit=0)
    tb.reset(CTRL, bit=0)
    tb.read_check(CRC, 0x00000000)

    # Feed 256-byte ramp
    for i in range(256):
        tb.write(DATA, i)
    expected_crc3 = zlib.crc32(bytes(range(256))) & 0xFFFFFFFF
    tb.read_check(CRC, expected_crc3)
    tb.read_check(COUNT, 256)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"ANVIL torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("anvil", firmware, mod_dir / "top.sv")
    ok, luts = build_module("anvil", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("anvil")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
