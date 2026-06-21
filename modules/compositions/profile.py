#!/usr/bin/env python3
"""OBSERVE image regression: Profile.

Run a fibonacci workload while observe modules watch the bus.
Reads back all 9 observe modules with labelled output.

Usage:
    python modules/compositions/profile.py --gen-only
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rime-i"))

_gf_src = (Path(__file__).resolve().parent.parent / "rime-i" / "gen_firmware.py").read_text()
_gf_ns = {}
exec(_gf_src.split("\ndef generate_math_firmware")[0], _gf_ns)
RV32I = _gf_ns["RV32I"]

x0, ra, sp = 0, 1, 2
t0, t1, t2 = 5, 6, 7
a0, a1 = 10, 11
s0, s1, s2, s3, s4, s5, s6, s7 = 8, 9, 18, 19, 20, 21, 22, 23

UART = 0x20000000

SCRY   = 0x30000000
ECHO   = 0x31000000
HEAT   = 0x32000000
EPOCH  = 0x33000000
LATCH  = 0x34000000
PRISM  = 0x35000000
TRAP   = 0x36000000
GAUGE  = 0x37000000
DEPTH  = 0x38000000

OBS_MODULES = ["scry", "echo", "heat", "epoch", "latch", "prism", "trap", "gauge", "depth"]


def emit_prelude(asm):
    asm.lui(sp, 0x00001)
    asm.lui(s4, 0x20000)
    asm.j("main")

    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    asm.label("puthex")
    asm.addi(sp, sp, -12)
    asm.sw(ra, sp, 8)
    asm.sw(s0, sp, 4)
    asm.sw(s1, sp, 0)
    asm.mv(s0, a0)
    asm.addi(s1, x0, 28)
    asm.label("ph_loop")
    asm.blt(s1, x0, "ph_done")
    asm.srl(a0, s0, s1)
    asm.andi(a0, a0, 0xF)
    asm.addi(t0, x0, 10)
    asm.blt(a0, t0, "ph_digit")
    asm.addi(a0, a0, ord('A') - 10)
    asm.j("ph_emit")
    asm.label("ph_digit")
    asm.addi(a0, a0, ord('0'))
    asm.label("ph_emit")
    asm.call("putc")
    asm.addi(s1, s1, -4)
    asm.j("ph_loop")
    asm.label("ph_done")
    asm.lw(s1, sp, 0)
    asm.lw(s0, sp, 4)
    asm.lw(ra, sp, 8)
    asm.addi(sp, sp, 12)
    asm.ret()


def print_label(asm, label, value_reg):
    for ch in label:
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, ord(':'))
    asm.call("putc")
    asm.mv(a0, value_reg)
    asm.call("puthex")
    asm.addi(a0, x0, 10)
    asm.call("putc")


def generate_firmware():
    asm = RV32I()
    emit_prelude(asm)

    asm.label("main")

    # Reset and enable all observers BEFORE workload
    # SCRY: clear + enable
    asm.li(t0, SCRY + 0x004)
    asm.addi(t1, x0, 3)            # bit0=enable, bit1=clear
    asm.sw(t1, t0, 0)
    asm.li(t0, SCRY + 0x004)
    asm.addi(t1, x0, 1)            # enable only
    asm.sw(t1, t0, 0)

    # ECHO: clear + enable
    asm.li(t0, ECHO + 0x000)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)
    asm.li(t0, ECHO + 0x000)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # HEAT: clear + enable
    asm.li(t0, HEAT + 0x000)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)
    asm.li(t0, HEAT + 0x000)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # LATCH: reset event counter
    asm.li(t0, LATCH + 0x008)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)

    # TRAP: reset, set match for LATCH EVENT addr, enable bp0
    asm.li(t0, TRAP + 0x020)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, TRAP + 0x000)
    asm.li(t1, LATCH + 0x014)
    asm.sw(t1, t0, 0)
    asm.li(t0, TRAP + 0x010)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # GAUGE: reset, gate, start
    asm.li(t0, GAUGE + 0x018)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, GAUGE + 0x000)
    asm.li(t1, 50000)
    asm.sw(t1, t0, 0)
    asm.li(t0, GAUGE + 0x018)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # DEPTH: configure base/mask covering BRAM range, reset, enable
    asm.li(t0, DEPTH + 0x000)
    asm.sw(x0, t0, 0)
    asm.li(t0, DEPTH + 0x004)
    asm.li(t1, 0xFFFFF000)
    asm.sw(t1, t0, 0)
    asm.li(t0, DEPTH + 0x018)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)

    # === Workload: fibonacci(10) firing LATCH events ===
    asm.addi(s5, x0, 0)
    asm.addi(s6, x0, 1)
    asm.addi(s7, x0, 10)
    asm.label("fib_loop")
    asm.add(t2, s5, s6)
    asm.mv(s5, s6)
    asm.mv(s6, t2)
    asm.li(t0, LATCH + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.addi(s7, s7, -1)
    asm.bne(s7, x0, "fib_loop")

    # === Read observations ===

    # EPOCH uptime
    asm.li(t0, EPOCH + 0x018)
    asm.lw(s0, t0, 0)
    print_label(asm, "EPOCH", s0)

    # LATCH events
    asm.li(t0, LATCH + 0x018)
    asm.lw(s0, t0, 0)
    print_label(asm, "LATCH", s0)

    # GAUGE running count of bus transactions
    asm.li(t0, GAUGE + 0x014)
    asm.lw(s0, t0, 0)
    print_label(asm, "GAUGE", s0)

    # GAUGE per-direction breakdown from the last completed gate.
    # Exercises the read/write counters added in cure list item #9.
    # Values vary with the workload but must both be > 0 and sum to TOTAL.
    asm.li(t0, GAUGE + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "GAUGER", s0)
    asm.li(t0, GAUGE + 0x00C)
    asm.lw(s0, t0, 0)
    print_label(asm, "GAUGEW", s0)

    # TRAP match count (should be exactly 10)
    asm.li(t0, TRAP + 0x01C)
    asm.lw(s0, t0, 0)
    print_label(asm, "TRAP", s0)

    # DEPTH samples
    asm.li(t0, DEPTH + 0x010)
    asm.lw(s0, t0, 0)
    print_label(asm, "DEPTH", s0)

    # SCRY trace count
    asm.li(t0, SCRY + 0x000)
    asm.lw(s0, t0, 0)
    print_label(asm, "SCRY", s0)

    # ECHO event count
    asm.li(t0, ECHO + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "ECHO", s0)

    # HEAT total transactions
    asm.li(t0, HEAT + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "HEAT", s0)

    # PRISM grayscale of 0x804020
    asm.li(t0, PRISM + 0x000)
    asm.li(t1, 0x00804020)
    asm.sw(t1, t0, 0)
    asm.li(t0, PRISM + 0x004)
    asm.lw(s0, t0, 0)
    print_label(asm, "PRISM", s0)

    for ch in "PROFILE:DONE":
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, 10)
    asm.call("putc")

    asm.li(t0, 0x100000)
    asm.label("_final_delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "_final_delay")
    asm.j("main")

    asm.resolve()
    return asm.code


def predict():
    return {
        "EPOCH":  None,        # uptime varies
        "LATCH":  10,          # 10 fib iterations fired events
        "GAUGE":  None,        # bus transaction count varies
        "GAUGER": None,        # read transactions in last gate (must be > 0 on silicon)
        "GAUGEW": None,        # write transactions in last gate (must be > 0 on silicon)
        "TRAP":   10,          # 10 matches on LATCH EVENT addr
        "DEPTH":  None,        # snoop sample count varies
        "SCRY":   None,        # trace count varies (saturates at 256)
        "ECHO":   None,        # event count saturates at 16
        "HEAT":   None,        # total transactions varies
        "PRISM":  None,        # grayscale formula HDL-specific
    }


def main():
    firmware = generate_firmware()
    print(f"Profile firmware: {len(firmware)} instructions ({len(firmware)*4} bytes)")
    print(f"BRAM usage: {len(firmware)}/1024 ({len(firmware)*100//1024}%)")
    expected = predict()
    print("Expected:")
    for label, val in expected.items():
        if val is None:
            print(f"  {label:6s}: variable")
        else:
            print(f"  {label:6s}: 0x{val:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
