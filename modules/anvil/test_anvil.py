#!/usr/bin/env python3
"""ANVIL compositor test: RIME-I + CRC-32 hardware accelerator.

Tests:
  1. CRC of empty (no bytes fed) = 0x00000000 after final XOR
  2. CRC of "RIME" = known value (computed offline)
  3. CRC of 256-byte ramp (0x00..0xFF), verify against Python zlib.crc32

All test vectors verified against Python's zlib.crc32.
"""

import sys
import zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

A_DATA = MOD_BASE + 0x000
A_CRC  = MOD_BASE + 0x004
A_CTRL = MOD_BASE + 0x008
A_COUNT = MOD_BASE + 0x010

# Precompute expected CRC values using Python
CRC_EMPTY = 0x00000000  # CRC of zero bytes
CRC_RIME = zlib.crc32(b"RIME") & 0xFFFFFFFF
CRC_RAMP = zlib.crc32(bytes(range(256))) & 0xFFFFFFFF


def gen_firmware():
    asm = RV32I()
    asm.lui(sp, 0x00001)
    asm.lui(s4, 0x20000)
    asm.j("main")

    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    asm.label("main")

    # --- Test 1: empty CRC = 0 ---
    asm.li(t0, A_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)  # reset

    asm.li(t0, A_CRC)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.bne(s0, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: CRC of "RIME" ---
    asm.label("test2")
    asm.li(t0, A_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    asm.li(t0, A_DATA)
    asm.addi(t1, x0, ord('R'))
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, ord('I'))
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, ord('M'))
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, ord('E'))
    asm.sw(t1, t0, 0)

    asm.li(t0, A_CRC)
    asm.lw(s0, t0, 0)
    asm.li(s1, CRC_RIME)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.bne(s0, s1, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: CRC of 0x00..0xFF (256 bytes) ---
    asm.label("test3")
    asm.li(t0, A_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    asm.li(t0, A_DATA)
    asm.addi(s0, x0, 0)    # byte value
    asm.li(s1, 256)
    asm.label("ramp")
    asm.bge(s0, s1, "ramp_done")
    asm.sw(s0, t0, 0)
    asm.addi(s0, s0, 1)
    asm.j("ramp")
    asm.label("ramp_done")

    asm.li(t0, A_CRC)
    asm.lw(s0, t0, 0)
    asm.li(s1, CRC_RAMP)

    # Also verify count = 256
    asm.li(t0, A_COUNT)
    asm.lw(s2, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(s0, s1, "t3f")
    asm.li(t0, 256)
    asm.bne(s2, t0, "t3f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("done")
    asm.label("t3f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    asm.label("done")
    asm.addi(a0, x0, 10)
    asm.call("putc")
    asm.li(t0, 0x200000)
    asm.label("delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "delay")
    asm.j("main")

    asm.resolve()
    return asm.code


def main():
    print(f"Expected CRC values: empty=0x{CRC_EMPTY:08X} RIME=0x{CRC_RIME:08X} ramp=0x{CRC_RAMP:08X}")
    firmware = gen_firmware()
    ok = run_module_test("anvil", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
