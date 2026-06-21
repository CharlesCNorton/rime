#!/usr/bin/env python3
"""ORACLE compositor test: RIME-I + lookup table interpolator.

Tests:
  1. Write table[0]=0, table[1]=1000. Query idx=0 frac=0 → 0.
  2. Same table. Query idx=0 frac=128 (0.5) → ~500.
  3. Write table[5]=12345. Query idx=5 frac=0 → 12345.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s4, MOD_BASE

O_QUERY  = MOD_BASE + 0x000
O_RESULT = MOD_BASE + 0x004
O_TABLE  = MOD_BASE + 0x400


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

    def query(val, reg):
        asm.li(t0, O_QUERY)
        asm.li(t1, val)
        asm.sw(t1, t0, 0)
        asm.li(t0, O_RESULT)
        asm.lw(reg, t0, 0)

    asm.label("main")

    # Load table: [0]=0, [1]=1000
    asm.li(t0, O_TABLE)
    asm.sw(x0, t0, 0)
    asm.li(t1, 1000)
    asm.sw(t1, t0, 4)

    # --- Test 1: query idx=0, frac=0 → 0 ---
    query(0x0000, s0)
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.bne(s0, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: query idx=0, frac=128 (0.5) → ~500 ---
    asm.label("test2")
    query(0x0080, s0)
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.li(t0, 450)
    asm.blt(s0, t0, "t2f")
    asm.li(t0, 550)
    asm.bge(s0, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: table[5]=12345, query exact ---
    asm.label("test3")
    asm.li(t0, O_TABLE + 5 * 4)
    asm.li(t1, 12345)
    asm.sw(t1, t0, 0)
    # Query: idx=5 means bits[13:8]=5 → value 0x0500
    query(0x0500, s0)
    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.li(t0, 12345)
    asm.bne(s0, t0, "t3f")
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
    ok = run_module_test("oracle", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
