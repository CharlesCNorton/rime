#!/usr/bin/env python3
"""FORGE compositor test: RIME-I + SHA-256 compression.

Tests:
  1. Hash input=0 → h0 is nonzero (compression changed the state)
  2. Hash input=1 → h0 differs from input=0 (avalanche)
  3. Hash same input twice → same result (deterministic)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

F_DATA = MOD_BASE + 0x000
F_CTRL = MOD_BASE + 0x004
F_STAT = MOD_BASE + 0x008
F_H0   = MOD_BASE + 0x00C


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

    _wc = [0]
    def hash_and_wait(input_val):
        n = _wc[0]
        _wc[0] += 1
        asm.li(t0, F_DATA)
        asm.li(t1, input_val)
        asm.sw(t1, t0, 0)
        asm.li(t0, F_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)
        lbl = f"hw{n}"
        asm.li(t0, F_STAT)
        asm.label(lbl)
        asm.lw(t1, t0, 0)
        asm.beq(t1, x0, lbl)

    asm.label("main")

    # --- Test 1: hash(0) → nonzero h0 ---
    hash_and_wait(0)
    asm.li(t0, F_H0)
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

    # --- Test 2: hash(1) differs from hash(0) ---
    asm.label("test2")
    hash_and_wait(1)
    asm.li(t0, F_H0)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.beq(s0, s1, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: hash(0) again → same as first time ---
    asm.label("test3")
    hash_and_wait(0)
    asm.li(t0, F_H0)
    asm.lw(s2, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(s0, s2, "t3f")
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
    ok = run_module_test("forge", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
