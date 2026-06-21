#!/usr/bin/env python3
"""TIDE compositor test: RIME-I + DDS waveform generator.

Tests:
  1. Square wave: enable, read sample, should be 0 or 255
  2. Sawtooth: read two samples, second > first (phase advancing)
  3. Sine: read sample at quarter point, should be near 128+127=255 (peak)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

T_FREQ = MOD_BASE + 0x000
T_WAVE = MOD_BASE + 0x004
T_SAMP = MOD_BASE + 0x008
T_PH   = MOD_BASE + 0x00C
T_CTRL = MOD_BASE + 0x010


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

    # --- Test 1: square wave, sample is 0 or 255 ---
    asm.li(t0, T_CTRL)
    asm.addi(t1, x0, 3)  # enable + reset
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 1)  # enable
    asm.sw(t1, t0, 0)

    asm.li(t0, T_FREQ)
    asm.li(t1, 0x10000000)  # fast frequency
    asm.sw(t1, t0, 0)

    asm.li(t0, T_WAVE)
    asm.addi(t1, x0, 1)  # square
    asm.sw(t1, t0, 0)

    # Small delay
    asm.li(t0, 100)
    asm.label("d1")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "d1")

    asm.li(t0, T_SAMP)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    # Sample should be 0 or 255
    asm.beq(s0, x0, "t1p")
    asm.addi(t0, x0, 255)
    asm.beq(s0, t0, "t1p")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1p")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 2: sawtooth, phase advances ---
    asm.label("test2")
    asm.li(t0, T_WAVE)
    asm.addi(t1, x0, 2)  # sawtooth
    asm.sw(t1, t0, 0)

    asm.li(t0, T_PH)
    asm.lw(s0, t0, 0)
    # Small delay
    asm.li(t0, 50)
    asm.label("d2")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "d2")
    asm.li(t0, T_PH)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    # Phase should have advanced (s1 != s0)
    asm.beq(s0, s1, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: sine wave, verify LUT at known phase points ---
    # Disable, sine mode, freq=0, write phase directly, read sample.
    #
    # Phase 0x00000000 -> sine_quarter[0]=0 -> output=128+0=128
    # Phase 0x1FC00000 -> sine_quarter[63]=127 -> output=128+127=255
    asm.label("test3")

    asm.li(t0, T_CTRL)
    asm.addi(t1, x0, 2)     # reset phase, disable
    asm.sw(t1, t0, 0)
    asm.li(t0, T_FREQ)
    asm.sw(x0, t0, 0)       # freq=0 (phase frozen)
    asm.li(t0, T_WAVE)
    asm.sw(x0, t0, 0)       # wave=0 (sine)

    # Write phase=0, enable, read sample: expect 128
    asm.li(t0, T_PH)
    asm.sw(x0, t0, 0)       # phase=0 directly
    asm.li(t0, T_CTRL)
    asm.addi(t1, x0, 1)     # enable
    asm.sw(t1, t0, 0)
    asm.li(t0, T_SAMP)
    asm.lw(s0, t0, 0)

    # Write phase=0x1FC00000 (quarter-peak: idx=63), read sample: expect 255
    asm.li(t0, T_PH)
    asm.li(t1, 0x1FC00000)
    asm.sw(t1, t0, 0)       # phase=quarter peak directly
    asm.li(t0, T_SAMP)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    # s0 should be 128, s1 should be 255
    asm.addi(t0, x0, 128)
    asm.bne(s0, t0, "t3f")
    asm.addi(t0, x0, 255)
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
    ok = run_module_test("tide", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
