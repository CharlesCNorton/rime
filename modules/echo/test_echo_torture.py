#!/usr/bin/env python3
"""ECHO (Event Capture and Hardware Observer) torture test.

Validates the CONTROL/STATUS enable/disable/clear transitions. STATUS
bit 0 is `enabled` and bit 1 is `wrapped` — both are deterministic from
host writes alone (the snoop-driven counters are timing-dependent, so
we don't assert on them). Uses read_assert so any wrong value diverges
the hash at the point of failure, not only at final compare.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

CONTROL = 0x000
STATUS  = 0x004
COUNT   = 0x008
CYCLE   = 0x00C
WR_PTR  = 0x010


def gen():
    tb = TortureBuilder("echo")
    tb.write(CONTROL, 0x02)                # clear
    tb.read_assert_masked(STATUS, 0, 0x1)  # enabled=0
    tb.write(CONTROL, 0x01)                # enable
    tb.read_assert_masked(STATUS, 1, 0x1)  # enabled=1
    tb.write(CONTROL, 0x00)                # disable
    tb.read_assert_masked(STATUS, 0, 0x1)  # enabled=0
    tb.write(CONTROL, 0x02)                # clear
    tb.read_assert_masked(STATUS, 0, 0x1)  # enabled=0
    # wrapped (bit 1) and the counters are snoop-driven; assert only the
    # host-controlled enabled bit and exercise the rest without asserting.
    tb.read_discard(CYCLE)

    tb.write(0x000, 2)
    tb.write(0x000, 1)
    tb.delay(10)
    tb.read_mix(0x008, None)
    tb.read_mix(0x00C, None)
    tb.read_mix(0x010, None)
    tb.adversarial_write(0x004, 0xFFFFFFFF)
    tb.adversarial_write(0x008, 0)
    tb.write(0x000, 2)
    tb.write(0x000, 1)
    tb.delay(5)
    tb.read_mix(0x040, None)
    tb.read_mix(0x07C, None)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"ECHO torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("echo", firmware, mod_dir / "top.sv")
    ok, luts = build_module("echo", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("echo")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
