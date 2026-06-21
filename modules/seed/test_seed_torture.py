#!/usr/bin/env python3
"""Torture test for SEED: SEED: Secure Entropy-Enhanced Derivation — monotonic counter + hash mixing for unique nonces

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder, u32

SEED_VAL = 0x000
NONCE    = 0x004
COUNTER  = 0x008
CONTROL  = 0x00C
STATUS   = 0x010


def fnv_mix(h, data):
    x = u32(h ^ data)
    return u32(x + (x << 1) + (x << 4) + (x << 7) + (x << 8) + (x << 24))


def gen():
    tb = TortureBuilder("seed")

    # Reset
    tb.write(CONTROL, 0x02)
    tb.read_check(COUNTER, 0)
    tb.read_check(STATUS, 0)

    # Set seed and generate first nonce
    tb.write(SEED_VAL, 0xDEADBEEF)
    tb.write(CONTROL, 0x01)
    expected_0 = fnv_mix(fnv_mix(0x811C9DC5, 0xDEADBEEF), 0)
    tb.read_check(NONCE, expected_0)
    tb.read_check(COUNTER, 1)
    tb.read_check(STATUS, 1)

    # Generate second nonce — counter should be 1
    tb.write(CONTROL, 0x01)
    expected_1 = fnv_mix(fnv_mix(0x811C9DC5, 0xDEADBEEF), 1)
    tb.read_check(NONCE, expected_1)
    tb.read_check(COUNTER, 2)

    # Nonces must be different
    # (verified by the hash chain — if both were the same, the hash would differ)

    # Change seed, generate
    tb.write(SEED_VAL, 0x00000000)
    tb.write(CONTROL, 0x01)
    expected_2 = fnv_mix(fnv_mix(0x811C9DC5, 0x00000000), 2)
    tb.read_check(NONCE, expected_2)

    # Reset counter, regenerate with same seed — should match original counter=0
    tb.write(CONTROL, 0x02)
    tb.write(SEED_VAL, 0xDEADBEEF)
    tb.write(CONTROL, 0x01)
    tb.read_check(NONCE, expected_0)

    # Adversarial: max seed
    tb.write(SEED_VAL, 0xFFFFFFFF)
    tb.write(CONTROL, 0x01)
    expected_ff = fnv_mix(fnv_mix(0x811C9DC5, 0xFFFFFFFF), 1)
    tb.read_check(NONCE, expected_ff)


    tb.write(0x00C, 2)
    tb.read_check(0x008, 0)
    tb.write(0x000, 0xDEADBEEF)
    tb.write(0x00C, 1)
    tb.delay(5)
    tb.read_mix(0x004, None)
    tb.read_check(0x008, 1)
    tb.write(0x00C, 1)
    tb.delay(5)
    tb.read_mix(0x004, None)
    tb.read_check(0x008, 2)
    tb.adversarial_write(0x004, 0)
    tb.adversarial_write(0x008, 0)
    tb.adversarial_write(0x010, 0)
    tb.write(0x000, 0)
    tb.write(0x00C, 1)
    tb.delay(5)
    tb.read_mix(0x004, None)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"SEED torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("seed", firmware, mod_dir / "top.sv")
    ok, luts = build_module("seed", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("seed")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
