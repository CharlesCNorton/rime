#!/usr/bin/env python3
"""VIGIL compositor test: RIME-I + Hamming(7,4) ECC.

Tests:
  1. Encode 0b1010, decode clean → same data, syndrome=0
  2. Flip one bit in codeword, decode → corrected, syndrome≠0
  3. Encode all 16 values, inject error in each, verify all correct after decode
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, t2, t3, a0, s0, s1, s2, s3, s4, MOD_BASE

V_ENC  = MOD_BASE + 0x000
V_CODE = MOD_BASE + 0x004
V_DEC  = MOD_BASE + 0x008
V_DATA = MOD_BASE + 0x00C
V_SYN  = MOD_BASE + 0x010
V_CORR = MOD_BASE + 0x014
V_CTRL = MOD_BASE + 0x018
V_ERRS = MOD_BASE + 0x01C


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

    # --- Test 1: encode 0b1010, decode clean ---
    asm.li(t0, V_ENC)
    asm.addi(t1, x0, 0b1010)
    asm.sw(t1, t0, 0)

    asm.li(t0, V_CODE)
    asm.lw(s0, t0, 0)  # codeword

    # Decode the clean codeword
    asm.li(t0, V_DEC)
    asm.sw(s0, t0, 0)

    asm.li(t0, V_DATA)
    asm.lw(s1, t0, 0)  # should be 0b1010 = 10
    asm.li(t0, V_SYN)
    asm.lw(s2, t0, 0)  # should be 0

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 10)
    asm.bne(s1, t0, "t1f")
    asm.bne(s2, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: flip bit 0, decode → corrected ---
    asm.label("test2")
    # s0 still has the codeword from test 1
    asm.addi(t2, x0, 1)
    # XOR s0 with 1 to flip bit 0
    # Use asm to emit raw XOR instruction: xor t1, s0, t2
    asm.code.append((0 << 25) | (t2 << 20) | (s0 << 15) | (4 << 12) | (t1 << 7) | 0x33)

    asm.li(t0, V_DEC)
    asm.sw(t1, t0, 0)

    asm.li(t0, V_DATA)
    asm.lw(s1, t0, 0)  # should still be 10 (corrected)
    asm.li(t0, V_SYN)
    asm.lw(s2, t0, 0)  # should be nonzero
    asm.li(t0, V_CORR)
    asm.lw(s3, t0, 0)  # should be 1

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 10)
    asm.bne(s1, t0, "t2f")
    asm.beq(s2, x0, "t2f")
    asm.beq(s3, x0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: encode+corrupt+decode all 16 values ---
    asm.label("test3")
    asm.li(t0, V_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)  # reset error counter

    asm.addi(s0, x0, 0)   # data value 0-15
    asm.addi(t3, x0, 0)   # mismatch count

    asm.label("t3loop")
    asm.addi(t0, x0, 16)
    asm.bge(s0, t0, "t3done")

    # Encode
    asm.li(t0, V_ENC)
    asm.sw(s0, t0, 0)
    asm.li(t0, V_CODE)
    asm.lw(t1, t0, 0)

    # Flip bit 2 (corrupt)
    asm.addi(t2, x0, 4)
    asm.code.append((0 << 25) | (t2 << 20) | (t1 << 15) | (4 << 12) | (t1 << 7) | 0x33)  # xor t1, t1, t2

    # Decode
    asm.li(t0, V_DEC)
    asm.sw(t1, t0, 0)
    asm.li(t0, V_DATA)
    asm.lw(t2, t0, 0)

    # Check decoded == original
    asm.bne(t2, s0, "t3mis")
    asm.j("t3next")
    asm.label("t3mis")
    asm.addi(t3, t3, 1)
    asm.label("t3next")
    asm.addi(s0, s0, 1)
    asm.j("t3loop")

    asm.label("t3done")
    # Also check error counter = 16
    asm.li(t0, V_ERRS)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(t3, x0, "t3f")
    asm.addi(t0, x0, 16)
    asm.bne(s1, t0, "t3f")
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
    firmware = gen_firmware()
    ok = run_module_test("vigil", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
