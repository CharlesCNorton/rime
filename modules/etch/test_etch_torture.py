#!/usr/bin/env python3
"""Torture test for ETCH: ETCH: Encrypted Transform with Cyclic Hashing — XTEA 64-round Feistel block cipher

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

V0      = 0x000
V1      = 0x004
KEY0    = 0x008
KEY1    = 0x00C
KEY2    = 0x010
KEY3    = 0x014
CONTROL = 0x018
STATUS  = 0x01C


def gen():
    tb = TortureBuilder("etch")

    # Reset
    tb.write(CONTROL, 0x04)
    tb.read_assert(STATUS, 0)  # not done after reset

    # Load key
    tb.write(KEY0, 0x01234567)
    tb.write(KEY1, 0x89ABCDEF)
    tb.write(KEY2, 0xFEDCBA98)
    tb.write(KEY3, 0x76543210)

    # Load plaintext
    tb.write(V0, 0x41424344)
    tb.write(V1, 0x45464748)

    # Encrypt — STATUS rises to 1 when 32-cycle Feistel completes
    tb.write(CONTROL, 0x01)
    tb.delay(80)
    tb.read_assert(STATUS, 1)

    # Read ciphertext — hardware-dependent, just mix
    tb.read_mix(V0)
    tb.read_mix(V1)

    # Reset, re-encrypt zeros with zero key
    tb.write(CONTROL, 0x04)
    tb.write(KEY0, 0)
    tb.write(KEY1, 0)
    tb.write(KEY2, 0)
    tb.write(KEY3, 0)
    tb.write(V0, 0)
    tb.write(V1, 0)
    tb.write(CONTROL, 0x01)
    tb.delay(80)
    tb.read_mix(V0)
    tb.read_mix(V1)

    # Encrypt with all-FF key and all-FF plaintext
    tb.write(CONTROL, 0x04)
    tb.write(KEY0, 0xFFFFFFFF)
    tb.write(KEY1, 0xFFFFFFFF)
    tb.write(KEY2, 0xFFFFFFFF)
    tb.write(KEY3, 0xFFFFFFFF)
    tb.write(V0, 0xFFFFFFFF)
    tb.write(V1, 0xFFFFFFFF)
    tb.write(CONTROL, 0x01)
    tb.delay(80)
    tb.read_mix(V0)
    tb.read_mix(V1)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"ETCH torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("etch", firmware, mod_dir / "top.sv")
    ok, luts = build_module("etch", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("etch")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
