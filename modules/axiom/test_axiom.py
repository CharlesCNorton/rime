#!/usr/bin/env python3
"""AXIOM compositor test: RIME-I + JSON token scanner.

Tests:
  1. Feed '{', token=1(lbrace), depth=1
  2. Feed '{"a":1}', verify depth returns to 0, offset=7
  3. Feed unmatched '}', verify error count > 0
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

A_IN   = MOD_BASE + 0x000
A_TOK  = MOD_BASE + 0x004
A_DEP  = MOD_BASE + 0x008
A_CTRL = MOD_BASE + 0x00C
A_OFF  = MOD_BASE + 0x010
A_ERR  = MOD_BASE + 0x014


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

    def feed(byte_val):
        asm.li(t0, A_IN)
        asm.addi(t1, x0, byte_val)
        asm.sw(t1, t0, 0)

    def reset():
        asm.li(t0, A_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: '{' → token=1, depth=1 ---
    reset()
    feed(0x7B)  # '{'
    asm.li(t0, A_TOK)
    asm.lw(s0, t0, 0)
    asm.li(t0, A_DEP)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 1)  # lbrace
    asm.bne(s0, t0, "t1f")
    asm.bne(s1, t0, "t1f")  # depth=1
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: '{"a":1}' → depth=0, offset=7 ---
    asm.label("test2")
    reset()
    for ch in [0x7B, 0x22, 0x61, 0x22, 0x3A, 0x31, 0x7D]:  # {"a":1}
        feed(ch)
    asm.li(t0, A_DEP)
    asm.lw(s0, t0, 0)
    asm.li(t0, A_OFF)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.bne(s0, x0, "t2f")  # depth should be 0
    asm.addi(t0, x0, 7)
    asm.bne(s1, t0, "t2f")  # offset should be 7
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: unmatched '}' → error ---
    asm.label("test3")
    reset()
    feed(0x7D)  # '}' without opening '{'
    asm.li(t0, A_ERR)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.beq(s0, x0, "t3f")  # errors should be > 0
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
    ok = run_module_test("axiom", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
