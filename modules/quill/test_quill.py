#!/usr/bin/env python3
"""QUILL compositor test: RIME-I + 4-channel byte buffer.

Tests:
  1. Push 3 bytes to ch0, verify count=3
  2. Switch to ch1, push 2, switch back to ch0, verify count still 3
  3. Pop from ch0, verify 'A', count decrements to 2
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

Q_TX   = MOD_BASE + 0x000
Q_CH   = MOD_BASE + 0x004
Q_STAT = MOD_BASE + 0x008
Q_RX   = MOD_BASE + 0x00C
Q_CNT  = MOD_BASE + 0x010
Q_CTRL = MOD_BASE + 0x014


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

    def select_ch(ch):
        asm.li(t0, Q_CH)
        asm.addi(t1, x0, ch)
        asm.sw(t1, t0, 0)

    def push(val):
        asm.li(t0, Q_TX)
        asm.addi(t1, x0, val)
        asm.sw(t1, t0, 0)

    def read_count(reg):
        asm.li(t0, Q_CNT)
        asm.lw(reg, t0, 0)

    def pop(reg):
        asm.li(t0, Q_RX)
        asm.lw(reg, t0, 0)

    asm.label("main")

    asm.li(t0, Q_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # --- Test 1 ---
    select_ch(0)
    push(0x41)
    push(0x42)
    push(0x43)
    read_count(s0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 3)
    asm.bne(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2 ---
    asm.label("test2")
    select_ch(1)
    push(0x58)
    push(0x59)
    select_ch(0)
    read_count(s0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 3)
    asm.bne(s0, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3 ---
    asm.label("test3")
    pop(s0)
    read_count(s1)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 0x41)
    asm.bne(s0, t0, "t3f")
    asm.addi(t0, x0, 2)
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
    ok = run_module_test("quill", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
