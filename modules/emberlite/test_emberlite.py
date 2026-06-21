#!/usr/bin/env python3
"""EMBER-LITE compositor test: RIME-I + ring-oscillator TRNG.

The collection register latches a new word only once 32 Von Neumann
debiased bits accumulate, and COUNT tracks completed words — so reads
must be paced against COUNT, not assumed to advance per access.

Tests:
  1. The entropy pipeline produces words (COUNT leaves zero).
  2. Two words latched across a COUNT advance differ.
  3. COUNT is monotonic (advances by at least 2 over a wait).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import (RV32I, run_module_test, x0, sp, t0, t1, t2, t3,
                             a0, s0, s1, s2, s4, MOD_BASE)

E_RAND = MOD_BASE + 0x000
E_BYTE = MOD_BASE + 0x004
E_CTRL = MOD_BASE + 0x008
E_CNT  = MOD_BASE + 0x00C

GUARD = 0x200000  # poll bound; a live ring exits in microseconds


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
    # Reset the collection pipeline so COUNT starts from zero.
    asm.li(t0, E_CTRL)
    asm.li(t1, 1)
    asm.sw(t1, t0, 0)

    # --- Test 1: the pipeline produces words (COUNT leaves zero) ---
    asm.li(t0, E_CNT)
    asm.li(t2, GUARD)
    asm.label("t1_poll")
    asm.lw(s0, t0, 0)
    asm.bne(s0, x0, "t1_pass")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "t1_poll")
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1_pass")
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 2: two words latched across a COUNT advance differ ---
    asm.label("test2")
    asm.li(t3, E_CNT)
    asm.li(t0, E_RAND)
    asm.lw(s1, t3, 0)        # count snapshot
    asm.lw(s0, t0, 0)        # word A
    asm.li(t2, GUARD)
    asm.label("t2_wait")
    asm.lw(t1, t3, 0)
    asm.bne(t1, s1, "t2_got")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "t2_wait")
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2_got")
    asm.lw(s1, t0, 0)        # word B
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.beq(s0, s1, "t2_fail")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2_fail")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: COUNT is monotonic (advances by at least 2) ---
    asm.label("test3")
    asm.li(t3, E_CNT)
    asm.lw(s0, t3, 0)        # c0
    asm.addi(s2, s0, 2)      # target c0 + 2
    asm.li(t2, GUARD)
    asm.label("t3_wait")
    asm.lw(s1, t3, 0)
    asm.bge(s1, s2, "t3_pass")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "t3_wait")
    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("done")
    asm.label("t3_pass")
    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(a0, x0, ord('P'))
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
    ok = run_module_test("emberlite", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
