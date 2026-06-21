#!/usr/bin/env python3
"""CHORD compositor test: RIME-I + 4-voice PWM synth.

Tests:
  1. Single voice, read sample — should alternate 0/amp as phase advances
  2. Two voices with different freqs — sample differs from single voice
  3. All 4 voices at max amp — sample saturates at 255
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s3, s4, MOD_BASE

C_V0F  = MOD_BASE + 0x000
C_V0A  = MOD_BASE + 0x004
C_V1F  = MOD_BASE + 0x008
C_V1A  = MOD_BASE + 0x00C
C_V2F  = MOD_BASE + 0x010
C_V2A  = MOD_BASE + 0x014
C_V3F  = MOD_BASE + 0x018
C_V3A  = MOD_BASE + 0x01C
C_SAMP = MOD_BASE + 0x020
C_CTRL = MOD_BASE + 0x024


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

    # --- Test 1: single voice, sample is 0 or 100 ---
    asm.li(t0, C_CTRL)
    asm.addi(t1, x0, 3)  # enable + reset
    asm.sw(t1, t0, 0)

    asm.li(t0, C_V0F)
    asm.li(t1, 0x10000000)  # fast
    asm.sw(t1, t0, 0)
    asm.li(t0, C_V0A)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)

    asm.li(t0, C_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    asm.li(t0, 100)
    asm.label("d1")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "d1")

    asm.li(t0, C_SAMP)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    # Sample should be 0 or 100
    asm.beq(s0, x0, "t1p")
    asm.addi(t0, x0, 100)
    asm.beq(s0, t0, "t1p")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1p")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 2: add second voice, sample changes ---
    asm.label("test2")
    asm.li(t0, C_V1F)
    asm.li(t1, 0x08000000)
    asm.sw(t1, t0, 0)
    asm.li(t0, C_V1A)
    asm.addi(t1, x0, 50)
    asm.sw(t1, t0, 0)

    asm.li(t0, 100)
    asm.label("d2")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "d2")

    # Read multiple samples to find one that's not 0 or 100
    asm.addi(s1, x0, 0)  # found_different
    asm.addi(s2, x0, 0)  # iterations
    asm.addi(s3, x0, 20)
    asm.label("t2loop")
    asm.bge(s2, s3, "t2done")
    asm.li(t0, C_SAMP)
    asm.lw(t1, t0, 0)
    # Check if sample is not 0 and not 100 (means voice 1 contributed)
    asm.beq(t1, x0, "t2next")
    asm.addi(t0, x0, 100)
    asm.beq(t1, t0, "t2next")
    asm.addi(s1, s1, 1)
    asm.label("t2next")
    asm.addi(s2, s2, 1)
    asm.j("t2loop")
    asm.label("t2done")

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.beq(s1, x0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: all 4 voices at 100 → saturates at 255 when all high ---
    asm.label("test3")
    # Set all 4 voices to same freq, amp=100
    asm.li(t0, C_V2F)
    asm.li(t1, 0x10000000)
    asm.sw(t1, t0, 0)
    asm.li(t0, C_V2A)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, C_V3F)
    asm.li(t1, 0x10000000)
    asm.sw(t1, t0, 0)
    asm.li(t0, C_V3A)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    # V0 and V1 already set. Same freq for all = all in phase.
    asm.li(t0, C_V1F)
    asm.li(t1, 0x10000000)
    asm.sw(t1, t0, 0)

    asm.li(t0, 200)
    asm.label("d3")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "d3")

    # Read several samples, at least one should be > 200 (4*100 saturated)
    asm.addi(s0, x0, 0)  # max seen
    asm.addi(s2, x0, 0)
    asm.addi(s3, x0, 20)
    asm.label("t3loop")
    asm.bge(s2, s3, "t3done")
    asm.li(t0, C_SAMP)
    asm.lw(t1, t0, 0)
    asm.bge(s0, t1, "t3skip")
    asm.mv(s0, t1)
    asm.label("t3skip")
    asm.addi(s2, s2, 1)
    asm.j("t3loop")
    asm.label("t3done")

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 200)
    asm.blt(s0, t0, "t3f")
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
    ok = run_module_test("chord", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
