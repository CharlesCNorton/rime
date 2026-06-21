#!/usr/bin/env python3
"""SCRY hash-based torture test.

Tests enable/disable, clear, count, write pointer, and trace readback.
COUNT and WRITE_PTR after clear are deterministic. Trace contents after
clear are zero. Enables then reads non-zero count to verify capture.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

COUNT     = 0x000
CONTROL   = 0x004
WRITE_PTR = 0x008
TRACE_0   = 0x400

def gen():
    tb = TortureBuilder("scry")

    # Clear and disable
    tb.write(CONTROL, 2)  # clear
    tb.read_check(COUNT, 0)
    tb.read_check(WRITE_PTR, 0)

    # Trace[0] after clear should be 0
    tb.read_check(TRACE_0, 0)

    # Enable capture
    tb.write(CONTROL, 1)

    # Do some bus activity (writes to SCRY registers themselves count as
    # transactions on the snoop bus). Each write/read is a bus transaction.
    tb.write(CONTROL, 1)  # another write = bus activity
    tb.write(CONTROL, 1)

    # Count should be non-zero now (captures from the bus activity above)
    tb.read_mix(COUNT, None)  # exact count depends on bus, but > 0

    # Disable, then clear
    tb.write(CONTROL, 0)  # disable
    tb.write(CONTROL, 2)  # clear
    tb.read_check(COUNT, 0)
    tb.read_check(WRITE_PTR, 0)

    # After clear, trace[0] is zero again
    tb.read_check(TRACE_0, 0)

    # Adversarial: read trace at high index
    tb.read_check(0x7FC, 0)  # trace[255] after clear = 0

    # Re-enable for a final capture burst
    tb.write(CONTROL, 1)
    tb.write(CONTROL, 1)
    tb.write(CONTROL, 0)  # disable

    # Write pointer should be non-zero
    tb.read_mix(WRITE_PTR, None)


    tb.write(0x004, 2)
    tb.write(0x004, 1)
    tb.delay(10)
    tb.read_mix(0x000, None)
    tb.read_mix(0x008, None)
    tb.read_mix(0x400, None)
    tb.read_mix(0x404, None)
    tb.read_mix(0x7FC, None)
    tb.adversarial_write(0x000, 0)
    tb.adversarial_write(0x008, 0)
    tb.write(0x004, 2)
    tb.read_check(0x000, 0)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"SCRY torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("scry", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("scry", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("scry")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
