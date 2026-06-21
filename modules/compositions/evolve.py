#!/usr/bin/env python3
"""SIM image regression: Evolve.

Exercises all 11 modules of the sim composition with known inputs and
prints labelled hex readbacks.

Usage:
    python modules/compositions/evolve.py --gen-only
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

AUGUR     = 0x30000000
CELL      = 0x31000000
DICE      = 0x32000000
EMBERLITE = 0x33000000
EPOCH     = 0x34000000
FLOCK     = 0x35000000
FLUX      = 0x36000000
HAZE      = 0x37000000
MOSS      = 0x38000000
ORACLE    = 0x39000000
SPARK     = 0x3A000000

SIM_MODULES = [
    "augur", "cell", "dice", "emberlite", "epoch", "flock",
    "flux", "haze", "moss", "oracle", "spark",
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

    # CELL: Rule 30, init bit 32, step once
    asm.li(t0, CELL + 0x00C)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, CELL + 0x008)
    asm.addi(t1, x0, 30)
    asm.sw(t1, t0, 0)              # rule 30
    asm.li(t0, CELL + 0x000)
    asm.sw(x0, t0, 0)              # state[31:0] = 0
    asm.li(t0, CELL + 0x004)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # state[63:32] = 1 (bit 32 set)
    asm.li(t0, CELL + 0x00C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # step
    asm.li(t0, CELL + 0x000)
    asm.lw(s0, t0, 0)
    print_label(asm, "CELL", s0)

    # SPARK: 8 inputs = 1..8, 8 weights = 1, bias = 0 -> sum = 36
    asm.li(t0, SPARK + 0x044)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    for i in range(8):
        asm.li(t0, SPARK + i * 4)
        asm.addi(t1, x0, i + 1)
        asm.sw(t1, t0, 0)
        asm.li(t0, SPARK + 0x020 + i * 4)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)
    asm.li(t0, SPARK + 0x040)
    asm.sw(x0, t0, 0)
    asm.li(t0, SPARK + 0x044)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t2, 30)
    asm.label("sp_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "sp_w")
    asm.li(t0, SPARK + 0x04C)
    asm.lw(s0, t0, 0)
    print_label(asm, "SPARK", s0)

    # DICE: stochastic multiply 0xC0 * 0x80 ~ 0x60
    asm.li(t0, DICE + 0x00C)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, DICE + 0x000)
    asm.li(t1, 0xC0)
    asm.sw(t1, t0, 0)
    asm.li(t0, DICE + 0x004)
    asm.li(t1, 0x80)
    asm.sw(t1, t0, 0)
    asm.li(t0, DICE + 0x00C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t2, 400)
    asm.label("dice_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "dice_w")
    asm.li(t0, DICE + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "DICE", s0)

    # HAZE: noise at (0x100, 0x200)
    asm.li(t0, HAZE + 0x008)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, HAZE + 0x000)
    asm.li(t1, 0x0100)
    asm.sw(t1, t0, 0)
    asm.li(t0, HAZE + 0x004)
    asm.li(t1, 0x0200)
    asm.sw(t1, t0, 0)
    asm.li(t0, HAZE + 0x008)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t2, 30)
    asm.label("haze_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "haze_w")
    asm.li(t0, HAZE + 0x010)
    asm.lw(s0, t0, 0)
    print_label(asm, "HAZE", s0)

    # EPOCH uptime
    asm.li(t0, EPOCH + 0x018)
    asm.lw(s0, t0, 0)
    print_label(asm, "EPOCH", s0)

    # AUGUR: reset, set target, step 16 times, read STEPS and CHAIN0
    asm.li(t0, AUGUR + 0x010)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, AUGUR + 0x020)
    asm.li(t1, 0x4000)
    asm.sw(t1, t0, 0)              # TARGET
    asm.li(t0, AUGUR + 0x010)
    asm.addi(t1, x0, 1)
    for _ in range(16):
        asm.sw(t1, t0, 0)          # step (each write = one step)
    asm.li(t0, AUGUR + 0x014)
    asm.lw(s0, t0, 0)              # STEPS
    print_label(asm, "AUGUR", s0)

    # FLOCK: reset, step 4 times, read X0
    asm.li(t0, FLOCK + 0x008)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, FLOCK + 0x000)
    asm.addi(t1, x0, 1)
    for _ in range(4):
        asm.sw(t1, t0, 0)          # step
    asm.li(t0, FLOCK + 0x004)
    asm.lw(s0, t0, 0)              # STATUS = step count
    print_label(asm, "FLOCK", s0)

    # FLUX: PID Kp=1.0, setpoint=100, measured=50, expect output=50
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

    # MOSS: clear, set up a glider/blinker, step, read ALIVE
    asm.li(t0, MOSS + 0x020)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # clear
    # Blinker: 3 in a row at row 1
    asm.li(t0, MOSS + 0x004)       # ROW1
    asm.addi(t1, x0, 0x07)         # bits 0,1,2 set
    asm.sw(t1, t0, 0)
    asm.li(t0, MOSS + 0x020)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # step
    asm.li(t0, MOSS + 0x028)
    asm.lw(s0, t0, 0)              # ALIVE (blinker rotates, still 3)
    print_label(asm, "MOSS", s0)

    # ORACLE: identity table, query 0x2080 -> 0x2080
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

    # EMBERLITE: read entropy
    asm.li(t2, 5000)
    asm.label("el_warm")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "el_warm")
    asm.li(t0, EMBERLITE + 0x000)
    asm.lw(s0, t0, 0)
    print_label(asm, "EMBERL", s0)

    for ch in "EVOLVE:DONE":
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
        "CELL":   0x80000000,  # Rule 30 single seed at bit 32
        "SPARK":  36,          # 1+2+...+8 = 36
        "DICE":   None,        # stochastic, ~0x60 ± LFSR noise
        "HAZE":   None,        # HDL-specific noise interpolation
        "EPOCH":  None,        # uptime varies
        "AUGUR":  16,          # 16 steps
        "FLOCK":  4,           # 4 step writes -> step count = 4
        "FLUX":   50,          # Kp=1.0 * (100-50)
        "MOSS":   3,           # blinker has 3 alive cells in any phase
        "ORACLE": 0x2080,      # identity table query
        "EMBERL": None,        # hardware entropy
    }


def main():
    firmware = generate_firmware()
    print(f"Evolve firmware: {len(firmware)} instructions ({len(firmware)*4} bytes)")
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
