#!/usr/bin/env python3
"""LACE hash-based torture test.

Threads a running hash through every LACE operation: 2D encode/decode,
3D encode/decode, identity cases, boundary values, round-trip verification.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder, u32

X2D     = 0x000
Y2D     = 0x004
Z2D_OUT = 0x008
Z2D_IN  = 0x00C
X2D_OUT = 0x010
Y2D_OUT = 0x014
X3D     = 0x018
Y3D     = 0x01C
Z3D     = 0x020
M3D_OUT = 0x024
M3D_IN  = 0x028
X3D_OUT = 0x02C
Y3D_OUT = 0x030
Z3D_OUT = 0x034


def interleave_2d(x, y):
    z = 0
    for i in range(16):
        z |= ((x >> i) & 1) << (2 * i)
        z |= ((y >> i) & 1) << (2 * i + 1)
    return u32(z)


def deinterleave_2d(z):
    x = y = 0
    for i in range(16):
        x |= ((z >> (2 * i)) & 1) << i
        y |= ((z >> (2 * i + 1)) & 1) << i
    return x & 0xFFFF, y & 0xFFFF


def interleave_3d(x, y, z):
    m = 0
    for i in range(10):
        m |= ((x >> i) & 1) << (3 * i)
        m |= ((y >> i) & 1) << (3 * i + 1)
        m |= ((z >> i) & 1) << (3 * i + 2)
    return m & 0x3FFFFFFF


def deinterleave_3d(m):
    x = y = z = 0
    for i in range(10):
        x |= ((m >> (3 * i)) & 1) << i
        y |= ((m >> (3 * i + 1)) & 1) << i
        z |= ((m >> (3 * i + 2)) & 1) << i
    return x & 0x3FF, y & 0x3FF, z & 0x3FF


def gen():
    tb = TortureBuilder("lace")

    # --- 2D: identity cases ---
    # (0, 0) -> 0
    tb.write(X2D, 0)
    tb.write(Y2D, 0)
    tb.read_check(Z2D_OUT, interleave_2d(0, 0))

    # (1, 0) -> 1
    tb.write(X2D, 1)
    tb.write(Y2D, 0)
    tb.read_check(Z2D_OUT, interleave_2d(1, 0))

    # (0, 1) -> 2
    tb.write(X2D, 0)
    tb.write(Y2D, 1)
    tb.read_check(Z2D_OUT, interleave_2d(0, 1))

    # (1, 1) -> 3
    tb.write(X2D, 1)
    tb.write(Y2D, 1)
    tb.read_check(Z2D_OUT, interleave_2d(1, 1))

    # --- 2D: boundary values ---
    # (0xFFFF, 0x0000) -> alternating bits
    tb.write(X2D, 0xFFFF)
    tb.write(Y2D, 0x0000)
    tb.read_check(Z2D_OUT, interleave_2d(0xFFFF, 0x0000))

    # (0x0000, 0xFFFF) -> alternating bits (shifted)
    tb.write(X2D, 0x0000)
    tb.write(Y2D, 0xFFFF)
    tb.read_check(Z2D_OUT, interleave_2d(0x0000, 0xFFFF))

    # (0xFFFF, 0xFFFF) -> all ones
    tb.write(X2D, 0xFFFF)
    tb.write(Y2D, 0xFFFF)
    tb.read_check(Z2D_OUT, 0xFFFFFFFF)

    # --- 2D: decode round-trip ---
    test_z = interleave_2d(0x1234, 0x5678)
    tb.write(Z2D_IN, test_z)
    tb.read_check(X2D_OUT, 0x1234)
    tb.read_check(Y2D_OUT, 0x5678)

    # Decode boundary
    tb.write(Z2D_IN, 0xFFFFFFFF)
    tb.read_check(X2D_OUT, 0xFFFF)
    tb.read_check(Y2D_OUT, 0xFFFF)

    tb.write(Z2D_IN, 0x00000000)
    tb.read_check(X2D_OUT, 0x0000)
    tb.read_check(Y2D_OUT, 0x0000)

    # --- 2D: encode-decode round-trip with multiple values ---
    for x, y in [(0x00AA, 0x0055), (0x8000, 0x0001), (0x7FFF, 0x7FFF)]:
        z = interleave_2d(x, y)
        tb.write(X2D, x)
        tb.write(Y2D, y)
        tb.read_check(Z2D_OUT, z)
        tb.write(Z2D_IN, z)
        tb.read_check(X2D_OUT, x)
        tb.read_check(Y2D_OUT, y)

    # --- 3D: identity cases ---
    tb.write(X3D, 0)
    tb.write(Y3D, 0)
    tb.write(Z3D, 0)
    tb.read_check(M3D_OUT, 0)

    tb.write(X3D, 1)
    tb.write(Y3D, 0)
    tb.write(Z3D, 0)
    tb.read_check(M3D_OUT, interleave_3d(1, 0, 0))

    tb.write(X3D, 0)
    tb.write(Y3D, 1)
    tb.write(Z3D, 0)
    tb.read_check(M3D_OUT, interleave_3d(0, 1, 0))

    tb.write(X3D, 0)
    tb.write(Y3D, 0)
    tb.write(Z3D, 1)
    tb.read_check(M3D_OUT, interleave_3d(0, 0, 1))

    # --- 3D: boundary ---
    tb.write(X3D, 0x3FF)
    tb.write(Y3D, 0x3FF)
    tb.write(Z3D, 0x3FF)
    tb.read_check(M3D_OUT, 0x3FFFFFFF)

    # --- 3D: decode round-trip ---
    m = interleave_3d(0x15A, 0x2B7, 0x3E9)
    tb.write(M3D_IN, m)
    tb.read_check(X3D_OUT, 0x15A)
    tb.read_check(Y3D_OUT, 0x2B7)
    tb.read_check(Z3D_OUT, 0x3E9)

    # --- 3D: encode-decode round-trip ---
    for x, y, z in [(0x001, 0x002, 0x003), (0x155, 0x2AA, 0x000), (0x3FF, 0x000, 0x3FF)]:
        m = interleave_3d(x, y, z)
        tb.write(X3D, x)
        tb.write(Y3D, y)
        tb.write(Z3D, z)
        tb.read_check(M3D_OUT, m)
        tb.write(M3D_IN, m)
        tb.read_check(X3D_OUT, x)
        tb.read_check(Y3D_OUT, y)
        tb.read_check(Z3D_OUT, z)

    # --- Adversarial: oversize values (should be masked) ---
    tb.adversarial_write(X2D, 0xFFFFFFFF)  # only low 16 bits matter
    tb.write(Y2D, 0)
    tb.read_check(Z2D_OUT, interleave_2d(0xFFFF, 0))

    tb.adversarial_write(X3D, 0xFFFFFFFF)  # only low 10 bits matter
    tb.write(Y3D, 0)
    tb.write(Z3D, 0)
    tb.read_check(M3D_OUT, interleave_3d(0x3FF, 0, 0))

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"LACE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("lace", firmware, mod_dir / "top.sv")
    ok, luts = build_module("lace", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("lace")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
