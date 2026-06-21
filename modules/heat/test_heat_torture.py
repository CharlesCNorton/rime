#!/usr/bin/env python3
"""HEAT (Hardware Execution Activity Tracker) torture test.

Validates CONTROL/STATUS transitions. STATUS returns {any_sat, enabled}
— both deterministic from host writes (the snoop-driven page counters
and TOTAL are timing-dependent and left out of the assertions).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

CONTROL = 0x000
STATUS  = 0x004
TOTAL   = 0x008
PAGE    = 0x400


def gen():
    tb = TortureBuilder("heat")
    tb.write(CONTROL, 0x02)         # clear
    tb.read_assert(STATUS, 0)       # enabled=0, any_sat=0
    tb.write(CONTROL, 0x01)         # enable
    tb.read_assert(STATUS, 1)       # enabled=1
    tb.write(CONTROL, 0x04)         # freeze (enable cleared by this write)
    tb.read_assert(STATUS, 0)       # enabled=0 after freeze-only write
    tb.write(CONTROL, 0x02)         # clear
    tb.read_assert(STATUS, 0)
    tb.read_discard(TOTAL)          # counter — not asserted

    tb.write(0x000, 2)
    tb.write(0x000, 1)
    tb.delay(10)
    tb.read_mix(0x008, None)
    tb.read_mix(0x040, None)
    tb.read_mix(0x07C, None)
    tb.adversarial_write(0x004, 0xFFFFFFFF)
    tb.adversarial_write(0x008, 0)
    tb.write(0x000, 4)
    tb.read_mix(0x008, None)
    tb.write(0x000, 2)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"HEAT torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("heat", firmware, mod_dir / "top.sv")
    ok, luts = build_module("heat", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("heat")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
