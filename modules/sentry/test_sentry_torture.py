#!/usr/bin/env python3
"""SENTRY hash-based torture test.

Configures regions, tests allowed/denied access, reads trap addresses,
verifies enable/disable and clear-trap behavior. All reads use read_check
with exact expected values.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

CHECK_ADDR  = 0x000
CHECK_MODE  = 0x004
RESULT      = 0x008
TRAP_ADDR   = 0x00C
CONTROL     = 0x010
REGION0_BASE = 0x020
REGION0_CFG  = 0x024
REGION1_BASE = 0x028
REGION1_CFG  = 0x02C

def gen():
    tb = TortureBuilder("sentry")

    # Disabled by default: any check should be allowed
    tb.write(CHECK_ADDR, 0x1000)
    tb.write(CHECK_MODE, 1)  # read mode
    tb.read_check(RESULT, 1)  # allowed=1, trapped=0

    # Enable MPU, no regions configured -> denied
    tb.write(CONTROL, 1)  # enable
    tb.write(CHECK_ADDR, 0x1000)
    tb.write(CHECK_MODE, 1)
    tb.read_check(RESULT, 2)  # allowed=0, trapped=1
    tb.read_check(TRAP_ADDR, 0x1000)

    # Clear trap
    tb.write(CONTROL, 3)  # enable + clear trap
    tb.read_check(RESULT, 0)  # allowed=0 (stale), trapped=0 (cleared)

    # Configure region 0: base=0x1000, size=0x100, R+W enabled
    tb.write(REGION0_BASE, 0x1000)
    tb.write(REGION0_CFG, 0x100 | (1 << 16) | (1 << 17) | (1 << 18))  # size=256, R, W, enabled

    # Check allowed read in region
    tb.write(CHECK_ADDR, 0x1050)
    tb.write(CHECK_MODE, 1)
    tb.read_check(RESULT, 1)  # allowed

    # Check allowed write in region
    tb.write(CHECK_ADDR, 0x10FF)
    tb.write(CHECK_MODE, 2)
    tb.read_check(RESULT, 1)

    # Check denied: address outside region
    tb.write(CHECK_ADDR, 0x2000)
    tb.write(CHECK_MODE, 1)
    tb.read_check(RESULT, 2)  # denied + trapped
    tb.read_check(TRAP_ADDR, 0x2000)

    # Configure region 1: base=0x2000, size=0x80, R only
    tb.write(REGION1_BASE, 0x2000)
    tb.write(REGION1_CFG, 0x80 | (1 << 16) | (1 << 18))  # size=128, R, no W, enabled

    # Clear trap, re-check
    tb.write(CONTROL, 3)
    tb.write(CHECK_ADDR, 0x2040)
    tb.write(CHECK_MODE, 1)  # read
    tb.read_check(RESULT, 1)  # allowed

    # Write to read-only region -> denied
    tb.write(CHECK_ADDR, 0x2040)
    tb.write(CHECK_MODE, 2)  # write mode
    tb.read_check(RESULT, 2)  # denied
    tb.read_check(TRAP_ADDR, 0x2040)

    # Adversarial: boundary values
    tb.adversarial_write(CHECK_ADDR, 0xFFFFFFFF)
    tb.write(CHECK_MODE, 1)
    tb.read_check(RESULT, 2)  # denied (way outside any region)

    tb.adversarial_write(CHECK_ADDR, 0x00000000)
    tb.write(CHECK_MODE, 1)
    tb.read_check(RESULT, 2)  # denied

    # Disable MPU -> everything allowed again
    tb.write(CONTROL, 2)  # clear trap, disable (bit 0 = 0)
    tb.write(CHECK_ADDR, 0xDEADBEEF)
    tb.write(CHECK_MODE, 1)
    tb.read_check(RESULT, 1)  # allowed when disabled

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"SENTRY torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("sentry", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("sentry", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("sentry")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
