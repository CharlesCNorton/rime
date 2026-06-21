#!/usr/bin/env python3
"""Torture test for FLUX: FLUX: hardware PID controller with anti-windup.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("flux")
    tb.write(0x018, 1)
    tb.write(0x00C, 256)
    tb.write(0x010, 0)
    tb.write(0x014, 0)
    tb.write(0x000, 100)
    tb.write(0x004, 0)
    tb.read_mix(0x008, None)
    tb.read_check(0x01C, 100)
    tb.write(0x004, 50)
    tb.read_check(0x01C, 50)
    tb.adversarial_write(0x000, 0xFFFF)
    tb.write(0x018, 1)

    # Adversarial: boundary setpoints and gains
    tb.write(0x00C, 1)       # Kp=1 (minimum gain)
    tb.write(0x010, 0)       # Ki=0
    tb.write(0x014, 0)       # Kd=0
    tb.write(0x000, 0x7FFF)  # large setpoint
    tb.write(0x004, 0)       # zero measurement
    tb.read_mix(0x008, None)
    tb.read_mix(0x01C, None)

    # Negative error: measurement > setpoint
    tb.write(0x000, 0)
    tb.write(0x004, 1000)
    tb.read_mix(0x008, None)

    # Max gains
    tb.write(0x00C, 0xFFFF)
    tb.write(0x010, 0xFFFF)
    tb.write(0x014, 0xFFFF)
    tb.write(0x000, 100)
    tb.write(0x004, 50)
    tb.read_mix(0x008, None)

    # Garbage to output register
    tb.adversarial_write(0x008, 0xDEADBEEF)
    tb.adversarial_write(0x01C, 0x12345678)

    tb.write(0x018, 1)  # reset
    return tb.finish()

def main():
    fw, exp = gen()
    print(f"FLUX torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("flux", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("flux", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("flux")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
