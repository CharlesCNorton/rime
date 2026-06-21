#!/usr/bin/env python3
"""Torture test for GAUGE: GAUGE: General Aggregated Utilization and Granular Estimator — bus bandwidth counter via snoop

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

GATE    = 0x000
TOTAL   = 0x004
RUNNING = 0x014
CONTROL = 0x018


def gen():
    tb = TortureBuilder("gauge")
    tb.write(CONTROL, 0x02)         # reset
    tb.read_assert(TOTAL, 0)
    tb.read_discard(RUNNING)
    # Set gate and start — snoop-driven counters are timing-dependent
    tb.write(GATE, 100)
    tb.write(CONTROL, 0x01)
    tb.delay(120)
    tb.read_discard(TOTAL)
    tb.read_discard(RUNNING)
    tb.write(CONTROL, 0x02)         # reset clears everything
    tb.read_assert(TOTAL, 0)
    tb.read_discard(RUNNING)

    tb.write(0x018, 2)
    tb.write(0x000, 100)
    tb.write(0x018, 1)
    tb.delay(200)
    tb.read_mix(0x004, None)
    tb.read_mix(0x008, None)
    tb.read_mix(0x00C, None)
    tb.read_check(0x010, 100)
    tb.adversarial_write(0x004, 0)
    tb.adversarial_write(0x008, 0)
    tb.adversarial_write(0x00C, 0)
    tb.write(0x018, 2)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"GAUGE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("gauge", firmware, mod_dir / "top.sv")
    ok, luts = build_module("gauge", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("gauge")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
