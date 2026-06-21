#!/usr/bin/env python3
"""GRAIL hash-based torture test.

Writes 8 leaf values, computes root hash, verifies against Python CRC-32
pairwise reduction. Tests multiple leaf sets including adversarial values.
"""
import sys
import zlib
import struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder


def merkle_pair(a: int, b: int) -> int:
    data = struct.pack("<II", a & 0xFFFFFFFF, b & 0xFFFFFFFF)
    return zlib.crc32(data) & 0xFFFFFFFF


def merkle_root(leaves: list[int]) -> int:
    level = [v & 0xFFFFFFFF for v in leaves]
    while len(level) > 1:
        level = [merkle_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def gen():
    tb = TortureBuilder("grail")

    # Test 1: sequential leaves 0x11111111 .. 0x88888888
    leaves1 = [(i + 1) * 0x11111111 for i in range(8)]
    for i, v in enumerate(leaves1):
        tb.write(i * 4, v)
    tb.write(0x020, 1)  # compute
    tb.delay(80)
    expected1 = merkle_root(leaves1)
    tb.read_check(0x028, expected1)

    # Also verify level1 node 0 (hash of leaf 0 + leaf 1)
    expected_l1_0 = merkle_pair(leaves1[0], leaves1[1])
    tb.read_check(0x02C, expected_l1_0)

    # Test 2: all-zero leaves
    for i in range(8):
        tb.write(i * 4, 0)
    tb.write(0x020, 1)
    tb.delay(80)
    expected2 = merkle_root([0] * 8)
    tb.read_check(0x028, expected2)

    # Test 3: adversarial boundary values
    leaves3 = [0xFFFFFFFF, 0x00000000, 0x80000000, 0x7FFFFFFF,
               0xDEADBEEF, 0xCAFEBABE, 0x01234567, 0x89ABCDEF]
    for i, v in enumerate(leaves3):
        tb.write(i * 4, v)
    tb.write(0x020, 1)
    tb.delay(80)
    expected3 = merkle_root(leaves3)
    tb.read_check(0x028, expected3)

    return tb.finish()


def main():
    fw, exp = gen()
    print(f"GRAIL torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("grail", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("grail", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("grail")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
