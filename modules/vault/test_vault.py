#!/usr/bin/env python3
"""VAULT compositor test: RIME-I + AES-128 (simplified single-round).

Tests:
  1. Encrypt all-zero plain+key → deterministic nonzero cipher
  2. Different key → different cipher
  3. Encrypt known block, verify cipher matches Python computation
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

V_P0   = MOD_BASE + 0x000
V_K0   = MOD_BASE + 0x010
V_CTRL = MOD_BASE + 0x020
V_STAT = MOD_BASE + 0x024
V_C0   = MOD_BASE + 0x028


def sbox_py(x):
    x = x & 0xFF
    inv = x
    inv ^= ((x << 1) | (x >> 7)) & 0xFF
    inv ^= ((x << 2) | (x >> 6)) & 0xFF
    inv ^= ((x << 3) | (x >> 5)) & 0xFF
    inv ^= ((x << 4) | (x >> 4)) & 0xFF
    inv ^= 0x63
    return inv & 0xFF


def sub_word_py(w):
    return (sbox_py(w >> 24) << 24) | (sbox_py((w >> 16) & 0xFF) << 16) | \
           (sbox_py((w >> 8) & 0xFF) << 8) | sbox_py(w & 0xFF)


# Expected cipher for plain=0, key=0
EXPECTED_C0 = sub_word_py(0 ^ 0)  # = sub_word(0) = sbox(0)^4


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

    def encrypt():
        asm.li(t0, V_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: all-zero → nonzero cipher ---
    for i in range(4):
        asm.li(t0, V_P0 + i * 4)
        asm.sw(x0, t0, 0)
        asm.li(t0, V_K0 + i * 4)
        asm.sw(x0, t0, 0)
    encrypt()
    asm.li(t0, V_C0)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.beq(s0, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: different key → different cipher ---
    asm.label("test2")
    asm.li(t0, V_K0)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)  # key[0] = 1
    encrypt()
    asm.li(t0, V_C0)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.beq(s0, s1, "t2f")  # must differ from test 1
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: verify cipher[0] matches Python for zero plain+key ---
    asm.label("test3")
    asm.li(t0, V_K0)
    asm.sw(x0, t0, 0)  # key[0] back to 0
    encrypt()
    asm.li(t0, V_C0)
    asm.lw(s0, t0, 0)
    asm.li(s1, EXPECTED_C0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(s0, s1, "t3f")
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
    print(f"Expected C0 for zero block: 0x{EXPECTED_C0:08X}")
    firmware = gen_firmware()
    ok = run_module_test("vault", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
