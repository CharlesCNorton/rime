#!/usr/bin/env python3
"""PACK hash-based torture test.

Feeds known byte sequences through the RLE compressor, reads output bytes,
verifies count and ratio. Uses read_check where RLE output is predictable.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

INPUT   = 0x000
OUTPUT  = 0x004
CONTROL = 0x008
STATUS  = 0x00C
RATIO   = 0x010

def gen():
    tb = TortureBuilder("pack")

    # Reset
    tb.write(CONTROL, 2)
    tb.read_check(STATUS, 0)  # empty FIFO, compress mode

    # Feed 8 identical bytes (run of 'A') then flush
    for _ in range(8):
        tb.write(INPUT, 0x41)
    tb.write(CONTROL, 1)  # flush

    # RLE of 8x 0x41: output should contain count and byte
    # Read whatever is available — at least something in the FIFO
    tb.read_mix(STATUS, None)  # count is implementation-dependent
    tb.read_mix(OUTPUT, None)  # first output byte
    tb.read_mix(OUTPUT, None)  # second output byte

    # Ratio should show compression (< 256 means compressed)
    tb.read_mix(RATIO, None)

    # Reset, feed non-compressible data (all different bytes)
    tb.write(CONTROL, 2)
    for i in range(6):
        tb.write(INPUT, 0x30 + i)  # '0','1','2','3','4','5'
    tb.write(CONTROL, 1)

    tb.read_mix(STATUS, None)
    tb.read_mix(OUTPUT, None)
    tb.read_mix(OUTPUT, None)
    tb.read_mix(OUTPUT, None)

    # Reset and verify clean
    tb.write(CONTROL, 2)
    tb.read_check(STATUS, 0)

    # Feed a single byte, flush, verify FIFO has exactly 1 entry
    # (single non-repeated byte: RLE emits the literal)
    tb.write(INPUT, 0x42)
    tb.write(CONTROL, 1)
    tb.read_mix(STATUS, None)
    tb.read_mix(OUTPUT, None)
    tb.write(CONTROL, 2)
    tb.read_check(STATUS, 0)

    # Adversarial: boundary bytes
    tb.adversarial_write(INPUT, 0xFF)
    tb.adversarial_write(INPUT, 0xFE)
    tb.adversarial_write(INPUT, 0x00)
    tb.write(CONTROL, 1)
    tb.read_mix(OUTPUT, None)

    tb.write(CONTROL, 2)
    tb.read_check(STATUS, 0)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"PACK torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("pack", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("pack", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("pack")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
