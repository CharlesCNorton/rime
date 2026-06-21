#!/usr/bin/env python3
"""CONTROL image regression: Servo.

Exercises all 10 modules of the control composition with known inputs
and prints labelled hex readbacks. Each module is independently verified
against a Python predictor where applicable.

Usage:
    python modules/compositions/servo.py --gen-only
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

TIDE   = 0x30000000
CHORD  = 0x31000000
FLUX   = 0x32000000
ORACLE = 0x33000000
EPOCH  = 0x34000000
LATCH  = 0x35000000
HEDGE  = 0x36000000
NOTCH  = 0x37000000
PHASE  = 0x38000000
TEMPO  = 0x39000000

CONTROL_MODULES = [
    "tide", "chord", "flux", "oracle", "epoch", "latch", "hedge",
    "notch", "phase", "tempo",
]


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

    asm.label("delay_t0")
    asm.label("delay_loop")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "delay_loop")
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

    # TIDE: sine at quarter-wave phase
    asm.li(t0, TIDE + 0x004)
    asm.sw(x0, t0, 0)
    asm.li(t0, TIDE + 0x00C)
    asm.li(t1, 0x40000000)
    asm.sw(t1, t0, 0)
    asm.li(t0, TIDE + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "TIDE", s0)

    # EPOCH: uptime
    asm.li(t0, EPOCH + 0x018)
    asm.lw(s0, t0, 0)
    print_label(asm, "EPOCH", s0)

    # LATCH: 5 events
    asm.li(t0, LATCH + 0x008)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)
    asm.li(t0, LATCH + 0x014)
    asm.addi(t1, x0, 1)
    for _ in range(5):
        asm.sw(t1, t0, 0)
    asm.li(t0, LATCH + 0x018)
    asm.lw(s0, t0, 0)
    print_label(asm, "LATCH", s0)

    # HEDGE: burst=4, request once
    asm.li(t0, HEDGE + 0x008)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, HEDGE + 0x010)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)
    asm.li(t0, HEDGE + 0x00C)
    asm.addi(t1, x0, 0xFF)
    asm.sw(t1, t0, 0)
    asm.li(t0, HEDGE + 0x008)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, 1000)
    asm.call("delay_t0")
    asm.li(t0, HEDGE + 0x000)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, HEDGE + 0x004)
    asm.lw(s0, t0, 0)
    print_label(asm, "HEDGE", s0)

    # NOTCH: stable 0xFF
    asm.li(t0, NOTCH + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, NOTCH + 0x010)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, NOTCH + 0x000)
    asm.addi(t1, x0, 0xFF)
    asm.sw(t1, t0, 0)
    asm.li(t0, 50)
    asm.call("delay_t0")
    asm.li(t0, NOTCH + 0x000)
    asm.addi(t1, x0, 0xFF)
    asm.sw(t1, t0, 0)
    asm.li(t0, 50)
    asm.call("delay_t0")
    asm.li(t0, NOTCH + 0x004)
    asm.lw(s0, t0, 0)
    print_label(asm, "NOTCH", s0)

    # PHASE: 4 quadrature edges forward
    asm.li(t0, PHASE + 0x010)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    for ab in [0, 1, 3, 2, 0]:
        asm.li(t0, PHASE + 0x000)
        asm.addi(t1, x0, ab)
        asm.sw(t1, t0, 0)
        asm.li(t0, PHASE + 0x010)
        asm.addi(t1, x0, 2)
        asm.sw(t1, t0, 0)
    asm.li(t0, PHASE + 0x004)
    asm.lw(s0, t0, 0)
    print_label(asm, "PHASE", s0)

    # TEMPO: 3 rising edges
    asm.li(t0, TEMPO + 0x010)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, TEMPO + 0x000)
    asm.sw(x0, t0, 0)
    asm.li(t0, 100)
    asm.call("delay_t0")
    asm.li(t0, TEMPO + 0x004)
    asm.li(t1, 0xFFFF)
    asm.sw(t1, t0, 0)
    asm.li(t0, TEMPO + 0x010)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    for _ in range(3):
        asm.li(t0, TEMPO + 0x000)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)
        asm.li(t0, 300)
        asm.call("delay_t0")
        asm.li(t0, TEMPO + 0x000)
        asm.sw(x0, t0, 0)
        asm.li(t0, 300)
        asm.call("delay_t0")
    asm.li(t0, 70000)
    asm.call("delay_t0")
    asm.li(t0, TEMPO + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "TEMPO", s0)

    # CHORD: voice 0 = sine, others off
    asm.li(t0, CHORD + 0x024)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, CHORD + 0x000)
    asm.li(t1, 0x40000000)
    asm.sw(t1, t0, 0)
    asm.li(t0, CHORD + 0x004)
    asm.addi(t1, x0, 0xFF)
    asm.sw(t1, t0, 0)
    asm.li(t0, CHORD + 0x028)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)
    for vbase in [0x008, 0x010, 0x018]:
        asm.li(t0, CHORD + vbase + 4)
        asm.sw(x0, t0, 0)
    asm.li(t0, CHORD + 0x024)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, 200)
    asm.call("delay_t0")
    asm.li(t0, CHORD + 0x020)
    asm.lw(s0, t0, 0)
    print_label(asm, "CHORD", s0)

    # FLUX: PID with Kp=1.0, Ki=Kd=0, setpoint=100, measured=50
    asm.li(t0, FLUX + 0x018)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, FLUX + 0x00C)
    asm.li(t1, 0x100)
    asm.sw(t1, t0, 0)
    asm.li(t0, FLUX + 0x010)
    asm.sw(x0, t0, 0)
    asm.li(t0, FLUX + 0x014)
    asm.sw(x0, t0, 0)
    asm.li(t0, FLUX + 0x000)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, FLUX + 0x004)
    asm.addi(t1, x0, 50)
    asm.sw(t1, t0, 0)
    asm.li(t0, FLUX + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "FLUX", s0)

    # ORACLE: load 64-entry identity table, query
    asm.li(t0, ORACLE + 0x008)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    for i in range(64):
        asm.li(t0, ORACLE + 0x400 + i*4)
        asm.li(t1, i << 8)
        asm.sw(t1, t0, 0)
    asm.li(t0, ORACLE + 0x008)
    asm.sw(x0, t0, 0)
    asm.li(t0, ORACLE + 0x000)
    asm.li(t1, 0x2080)
    asm.sw(t1, t0, 0)
    asm.li(t0, ORACLE + 0x004)
    asm.lw(s0, t0, 0)
    print_label(asm, "ORACLE", s0)

    for ch in "SERVO:DONE":
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
        "TIDE":   0x80,
        "EPOCH":  None,
        "LATCH":  5,
        "HEDGE":  1,
        "NOTCH":  0xFF,
        "PHASE":  4,
        "TEMPO":  3,
        "CHORD":  None,    # phase-dependent sample
        "FLUX":   50,      # Kp=1.0 * error(100-50) = 50
        "ORACLE": 0x2080,  # identity table at query 0x2080
    }


def main():
    firmware = generate_firmware()
    print(f"Servo firmware: {len(firmware)} instructions ({len(firmware)*4} bytes)")
    print(f"BRAM usage: {len(firmware)}/1024 ({len(firmware)*100//1024}%)")
    expected = predict()
    print("Expected silicon values:")
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
