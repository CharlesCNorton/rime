#!/usr/bin/env python3
"""CHORD hash-based torture test.

Configures multiple voices with different waveforms, exercises enable/reset,
reads samples after delays. Sample values are timing-dependent so read_mix
with None is used, but the test differentiates by configuring 4 voices
and testing all 4 waveform types + multi-voice mixing.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

V0_FREQ = 0x000
V0_AMP = 0x004
V1_FREQ = 0x008
V1_AMP = 0x00C
V2_FREQ = 0x010
V2_AMP = 0x014
V3_FREQ = 0x018
V3_AMP = 0x01C
SAMPLE  = 0x020
CONTROL = 0x024
V0_WAVE = 0x028
V1_WAVE = 0x02C
V2_WAVE = 0x030
V3_WAVE = 0x034

def gen():
    tb = TortureBuilder("chord")

    # Reset everything
    tb.write(CONTROL, 3)  # reset phases + enable

    # After reset with no voices configured, sample should be 0 (all amps default 0)
    tb.read_assert(SAMPLE, 0)

    # Voice 0: square wave, high freq, full amplitude
    tb.write(V0_FREQ, 0x40000000)  # quarter of phase per tick
    tb.write(V0_AMP, 255)
    tb.write(V0_WAVE, 0)  # square

    # Enable and sample
    tb.write(CONTROL, 1)
    tb.delay(20)
    tb.read_mix(SAMPLE, None)

    # Voice 1: saw wave
    tb.write(V1_FREQ, 0x20000000)
    tb.write(V1_AMP, 128)
    tb.write(V1_WAVE, 1)
    tb.delay(20)
    tb.read_mix(SAMPLE, None)

    # Voice 2: triangle
    tb.write(V2_FREQ, 0x10000000)
    tb.write(V2_AMP, 64)
    tb.write(V2_WAVE, 2)
    tb.delay(20)
    tb.read_mix(SAMPLE, None)

    # Voice 3: sine
    tb.write(V3_FREQ, 0x08000000)
    tb.write(V3_AMP, 200)
    tb.write(V3_WAVE, 3)
    tb.delay(20)
    tb.read_mix(SAMPLE, None)

    # Reset phases, re-read (different phase position)
    tb.write(CONTROL, 3)
    tb.write(CONTROL, 1)
    tb.delay(10)
    tb.read_mix(SAMPLE, None)

    # Kill voice 0 amplitude, sample should change
    tb.write(V0_AMP, 0)
    tb.delay(10)
    tb.read_mix(SAMPLE, None)

    # Full reset, verify silence
    tb.write(CONTROL, 3)  # reset
    tb.write(V0_AMP, 0)
    tb.write(V1_AMP, 0)
    tb.write(V2_AMP, 0)
    tb.write(V3_AMP, 0)
    tb.write(CONTROL, 1)
    tb.delay(5)
    tb.read_assert(SAMPLE, 0)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"CHORD torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("chord", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("chord", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("chord")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
