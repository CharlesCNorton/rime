#!/usr/bin/env python3
"""MARK compositor test: RIME-I + MARK silicon PUF.

Tests:
  1. Trigger measurement, check STATUS=done, read key is nonzero
  2. Trigger two measurements, check key is stable (hamming distance < 8)
  3. Trigger 10 measurements, verify key reproducibility (all identical)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, t2, t3, a0, s0, s1, s2, s3, s4, MOD_BASE

MARK_KEY_LO  = MOD_BASE + 0x000
MARK_KEY_HI  = MOD_BASE + 0x004
MARK_CTRL    = MOD_BASE + 0x008
MARK_STATUS  = MOD_BASE + 0x00C
MARK_HAMMING = MOD_BASE + 0x010


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

    # Helper: trigger measurement and wait for done
    asm.label("measure")
    asm.li(t0, MARK_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, MARK_STATUS)
    asm.label("mwait")
    asm.lw(t1, t0, 0)
    asm.beq(t1, x0, "mwait")
    asm.ret()

    asm.label("main")

    # --- Test 1: measure, check done, key != 0 ---
    asm.call("measure")
    asm.li(t0, MARK_KEY_LO)
    asm.lw(s0, t0, 0)
    asm.li(t0, MARK_KEY_HI)
    asm.lw(s1, t0, 0)
    # Check KEY_LO is nonzero (module forces bit 0 = 1)
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.bne(s0, x0, "t1p")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1p")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 2: measure again, check hamming < 8 ---
    asm.label("test2")
    asm.call("measure")
    asm.li(t0, MARK_HAMMING)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t1, x0, 8)
    asm.bge(s0, t1, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: 10 measurements, all must match first ---
    asm.label("test3")
    asm.call("measure")
    asm.li(t0, MARK_KEY_LO)
    asm.lw(s0, t0, 0)     # reference lo
    asm.li(t0, MARK_KEY_HI)
    asm.lw(s1, t0, 0)     # reference hi

    asm.addi(s2, x0, 0)   # mismatch count
    asm.addi(s3, x0, 0)   # iteration
    asm.addi(t3, x0, 10)

    asm.label("t3loop")
    asm.bge(s3, t3, "t3done")
    asm.call("measure")
    asm.li(t0, MARK_KEY_LO)
    asm.lw(t1, t0, 0)
    asm.li(t0, MARK_KEY_HI)
    asm.lw(t2, t0, 0)
    # Check match
    asm.bne(t1, s0, "t3mis")
    asm.bne(t2, s1, "t3mis")
    asm.j("t3next")
    asm.label("t3mis")
    asm.addi(s2, s2, 1)
    asm.label("t3next")
    asm.addi(s3, s3, 1)
    asm.j("t3loop")

    asm.label("t3done")
    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(s2, x0, "t3f")
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
    ok = run_module_test("mark", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
