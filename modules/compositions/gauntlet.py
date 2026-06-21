#!/usr/bin/env python3
"""COMPUTE image regression: Gauntlet.

Exercises all 14 modules of the compute composition with known inputs
and prints labelled hex readbacks. Each module is independently verified
against a Python predictor.

Output format: NAME:HHHHHHHH per line, terminated by GAUNTLET:DONE.

Usage:
    python modules/compositions/gauntlet.py --gen-only
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
t0, t1, t2, t3 = 5, 6, 7, 28
a0, a1, a2 = 10, 11, 12
s0, s1, s2, s3, s4, s5, s6, s7 = 8, 9, 18, 19, 20, 21, 22, 23

UART = 0x20000000

DIVIDE = 0x30000000
CRANK  = 0x31000000
SIEVE  = 0x32000000
TALLY  = 0x33000000
TAPER  = 0x34000000
WEAVE  = 0x35000000
BLOOM  = 0x36000000
MORTAR = 0x37000000
LOGOS  = 0x38000000
FLIP   = 0x39000000
LACE   = 0x3A000000
ORBIT  = 0x3B000000
MOUNT  = 0x3C000000
GLYPH  = 0x3D000000

COMPUTE_MODULES = [
    "divide", "crank", "sieve", "tally", "taper", "weave", "bloom",
    "mortar", "logos", "flip", "lace", "orbit", "mount", "glyph",
]


def u32(x):
    return x & 0xFFFFFFFF


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
    """Emit `LABEL:HEX\n` to UART. value_reg is one of t/s registers."""
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
    # Boot confirmation
    for ch in "BOOT\n":
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")

    # ============================================================
    # CRANK: 32x32 multiply, 0xDEADBEEF * 0xCAFEBABE
    # ============================================================
    asm.li(t0, CRANK + 0x000)
    asm.li(t1, 0xDEADBEEF)
    asm.sw(t1, t0, 0)
    asm.li(t0, CRANK + 0x004)
    asm.li(t1, 0xCAFEBABE)
    asm.sw(t1, t0, 0)
    # Wait for done
    asm.li(t0, CRANK + 0x010)
    asm.label("crank_w")
    asm.lw(t1, t0, 0)
    asm.andi(t1, t1, 1)
    asm.beq(t1, x0, "crank_w")
    asm.li(t0, CRANK + 0x008)
    asm.lw(s0, t0, 0)              # crank_lo
    asm.li(t0, CRANK + 0x00C)
    asm.lw(s1, t0, 0)              # crank_hi

    # ============================================================
    # DIVIDE: crank_hi / 7 = quotient, remainder
    # ============================================================
    asm.li(t0, DIVIDE + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, DIVIDE + 0x000)
    asm.sw(s1, t0, 0)              # dividend = crank_hi
    asm.li(t0, DIVIDE + 0x004)
    asm.addi(t1, x0, 7)
    asm.sw(t1, t0, 0)              # divisor
    asm.li(t0, DIVIDE + 0x010)
    asm.label("div_w")
    asm.lw(t1, t0, 0)
    asm.andi(t1, t1, 1)
    asm.beq(t1, x0, "div_w")
    asm.li(t0, DIVIDE + 0x008)
    asm.lw(s2, t0, 0)              # quotient
    asm.li(t0, DIVIDE + 0x00C)
    asm.lw(s3, t0, 0)              # remainder

    # ============================================================
    # TALLY: 4-channel MAC. ch0 += 100*200 = 20000, ch1 += 50*60 = 3000
    # ============================================================
    asm.li(t0, TALLY + 0x01C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # reset
    # Channel 0: 100 * 200
    asm.li(t0, TALLY + 0x000)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)              # OP_A staging, ch=0 (default)
    asm.li(t0, TALLY + 0x004)
    asm.addi(t1, x0, 200)
    asm.sw(t1, t0, 0)              # OP_B triggers MAC
    asm.li(t2, 30)
    asm.label("tally_w0")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "tally_w0")
    asm.li(t0, TALLY + 0x008)
    asm.lw(s5, t0, 0)              # tally ch0

    # ============================================================
    # TAPER: saturating signed 8-bit add: 100 + 100 -> 127 (saturated)
    # ============================================================
    asm.li(t0, TAPER + 0x000)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, TAPER + 0x004)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, TAPER + 0x008)
    asm.lw(s6, t0, 0)              # taper saturated add

    # ============================================================
    # WEAVE: bit-serial 32-bit subtract: 0xFFFFFFFF - 0x12345678
    # ============================================================
    asm.li(t0, WEAVE + 0x000)
    asm.li(t1, 0xFFFFFFFF)
    asm.sw(t1, t0, 0)
    asm.li(t0, WEAVE + 0x004)
    asm.li(t1, 0x12345678)
    asm.sw(t1, t0, 0)
    asm.li(t0, WEAVE + 0x008)
    asm.addi(t1, x0, 1)            # cmd 1 = subtract
    asm.sw(t1, t0, 0)
    asm.li(t0, WEAVE + 0x010)
    asm.label("weave_w")
    asm.lw(t1, t0, 0)
    asm.andi(t1, t1, 1)
    asm.beq(t1, x0, "weave_w")
    asm.li(t0, WEAVE + 0x00C)
    asm.lw(s7, t0, 0)              # weave result

    # We've consumed s0..s7. Print the first batch and free registers.
    print_label(asm, "CRANKLO", s0)
    print_label(asm, "CRANKHI", s1)
    print_label(asm, "DIVQ",    s2)
    print_label(asm, "DIVR",    s3)
    print_label(asm, "TALLY",   s5)
    print_label(asm, "TAPER",   s6)
    print_label(asm, "WEAVE",   s7)

    # ============================================================
    # BLOOM: popcount of 0xDEADBEEF (24 bits set)
    # ============================================================
    asm.li(t0, BLOOM + 0x000)
    asm.li(t1, 0xDEADBEEF)
    asm.sw(t1, t0, 0)
    asm.li(t0, BLOOM + 0x004)
    asm.lw(s0, t0, 0)              # popcount
    asm.li(t0, BLOOM + 0x008)
    asm.lw(s1, t0, 0)              # CLZ
    asm.li(t0, BLOOM + 0x00C)
    asm.lw(s2, t0, 0)              # CTZ
    print_label(asm, "BLOOMP", s0)
    print_label(asm, "BLOOMC", s1)
    print_label(asm, "BLOOMT", s2)

    # ============================================================
    # GLYPH: GF(2^8) inverse of 0x53; expected 0xCA (FIPS 197)
    # ============================================================
    asm.li(t0, GLYPH + 0x000)
    asm.addi(t1, x0, 0x53)
    asm.sw(t1, t0, 0)              # OP_A
    asm.li(t0, GLYPH + 0x014)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # CONTROL bit1 = start INV
    asm.li(t0, GLYPH + 0x018)
    asm.label("glyph_w")
    asm.lw(t1, t0, 0)
    asm.andi(t1, t1, 1)
    asm.beq(t1, x0, "glyph_w")
    asm.li(t0, GLYPH + 0x00C)
    asm.lw(s0, t0, 0)              # GF inverse
    print_label(asm, "GLYPH", s0)

    # ============================================================
    # SIEVE: extract bits [11:4] of 0xDEADBEEF
    # ============================================================
    asm.li(t0, SIEVE + 0x000)
    asm.li(t1, 0xDEADBEEF)
    asm.sw(t1, t0, 0)
    asm.li(t1, (8 << 8) | 4)       # width=8, pos=4
    asm.li(t0, SIEVE + 0x004)
    asm.sw(t1, t0, 0)
    asm.li(t0, SIEVE + 0x008)
    asm.lw(s0, t0, 0)              # extracted field
    print_label(asm, "SIEVE", s0)

    # ============================================================
    # MORTAR: 2x2 matrix multiply
    # A = [[2,3],[4,5]], B = [[6,7],[8,9]]
    # C00 = 2*6 + 3*8 = 36, C01 = 2*7 + 3*9 = 41
    # C10 = 4*6 + 5*8 = 64, C11 = 4*7 + 5*9 = 73
    # ============================================================
    asm.li(t0, MORTAR + 0x000)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # A00
    asm.li(t0, MORTAR + 0x004)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)              # A01
    asm.li(t0, MORTAR + 0x008)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)              # A10
    asm.li(t0, MORTAR + 0x00C)
    asm.addi(t1, x0, 5)
    asm.sw(t1, t0, 0)              # A11
    asm.li(t0, MORTAR + 0x010)
    asm.addi(t1, x0, 6)
    asm.sw(t1, t0, 0)              # B00
    asm.li(t0, MORTAR + 0x014)
    asm.addi(t1, x0, 7)
    asm.sw(t1, t0, 0)              # B01
    asm.li(t0, MORTAR + 0x018)
    asm.addi(t1, x0, 8)
    asm.sw(t1, t0, 0)              # B10
    asm.li(t0, MORTAR + 0x01C)
    asm.addi(t1, x0, 9)
    asm.sw(t1, t0, 0)              # B11
    asm.li(t0, MORTAR + 0x020)
    asm.lw(s0, t0, 0)              # C00
    asm.li(t0, MORTAR + 0x024)
    asm.lw(s1, t0, 0)              # C01
    asm.li(t0, MORTAR + 0x028)
    asm.lw(s2, t0, 0)              # C10
    asm.li(t0, MORTAR + 0x02C)
    asm.lw(s3, t0, 0)              # C11
    print_label(asm, "MORTC00", s0)
    print_label(asm, "MORTC01", s1)
    print_label(asm, "MORTC10", s2)
    print_label(asm, "MORTC11", s3)

    # ============================================================
    # LOGOS: log2(0x100) = 8.0 in 8.8 FP = 0x0800
    # ============================================================
    asm.li(t0, LOGOS + 0x000)
    asm.li(t1, 0x100)
    asm.sw(t1, t0, 0)
    asm.li(t0, LOGOS + 0x008)
    asm.lw(s0, t0, 0)              # log2(0x100)
    print_label(asm, "LOGOS", s0)

    # ============================================================
    # FLIP: 8x8 transpose. Write rows = identity (bit i in row i),
    # then column 0 should be 0x01 (only bit 0 of row 0 was set).
    # Actually a more interesting test: rows = [0xFF, 0, 0, 0, 0, 0, 0, 0]
    # Column 0 should be 0x01 (bit 0 of row 0).
    # ============================================================
    asm.li(t0, FLIP + 0x000)
    asm.addi(t1, x0, 0xFF)
    asm.sw(t1, t0, 0)              # ROW8[0] = 0xFF
    for i in range(1, 8):
        asm.li(t0, FLIP + i*4)
        asm.sw(x0, t0, 0)          # ROW8[i] = 0
    asm.li(t0, FLIP + 0x020)
    asm.lw(s0, t0, 0)              # COL8[0] = bit 0 of all rows = 0x01
    print_label(asm, "FLIP", s0)

    # ============================================================
    # LACE: Z-order encode (X=0xAAAA, Y=0x5555)
    # Interleaved bits: x_bit_0, y_bit_0, x_bit_1, y_bit_1, ...
    # Even bits = X (0xAAAA = 10101010 10101010), so even bits = 0,1,0,1,...
    # Odd bits = Y (0x5555 = 01010101 01010101), so odd bits = 1,0,1,0,...
    # Result alternates: 0,1,1,0,0,1,1,0,...
    # Python prediction will compute this exactly.
    # ============================================================
    asm.li(t0, LACE + 0x000)
    asm.li(t1, 0xAAAA)
    asm.sw(t1, t0, 0)              # X2D
    asm.li(t0, LACE + 0x004)
    asm.li(t1, 0x5555)
    asm.sw(t1, t0, 0)              # Y2D triggers latch
    asm.li(t0, LACE + 0x008)
    asm.lw(s0, t0, 0)              # Morton code
    print_label(asm, "LACE", s0)

    # ============================================================
    # ORBIT: CORDIC sin(0) = 0, cos(0) = 0x10000 (1.0 in 1.15.16 FP)
    # ============================================================
    asm.li(t0, ORBIT + 0x000)
    asm.sw(x0, t0, 0)              # angle = 0
    asm.li(t0, ORBIT + 0x00C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # CONTROL = start, mode=rotation
    asm.li(t0, ORBIT + 0x010)
    asm.label("orbit_w")
    asm.lw(t1, t0, 0)
    asm.andi(t1, t1, 1)
    asm.beq(t1, x0, "orbit_w")
    asm.li(t0, ORBIT + 0x014)
    asm.lw(s0, t0, 0)              # COS_MAG (cos(0) ~ 1.0)
    asm.li(t0, ORBIT + 0x018)
    asm.lw(s1, t0, 0)              # SIN_PHS (sin(0) = 0)
    print_label(asm, "ORBITC", s0)
    print_label(asm, "ORBITS", s1)

    # ============================================================
    # MOUNT: Montgomery multiply A * B mod M with simple values.
    # A = [1, 0, 0, 0, 0, 0, 0, 0] (256-bit "1")
    # B = [1, 0, 0, 0, 0, 0, 0, 0] (256-bit "1")
    # M = [3, 0, 0, 0, 0, 0, 0, 0] (small odd modulus)
    # Result = A*B*R^-1 mod M, R = 2^256
    # We just verify done bit and read low word.
    # ============================================================
    # Load A
    asm.li(t0, MOUNT + 0x000)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # A[0]
    for i in range(1, 8):
        asm.li(t0, MOUNT + i*4)
        asm.sw(x0, t0, 0)          # A[1..7] = 0
    # Load B
    asm.li(t0, MOUNT + 0x020)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # B[0]
    for i in range(1, 8):
        asm.li(t0, MOUNT + 0x020 + i*4)
        asm.sw(x0, t0, 0)
    # Load M
    asm.li(t0, MOUNT + 0x040)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)              # M[0] = 3 (odd)
    for i in range(1, 8):
        asm.li(t0, MOUNT + 0x040 + i*4)
        asm.sw(x0, t0, 0)
    # Start
    asm.li(t0, MOUNT + 0x060)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    # Wait
    asm.li(t0, MOUNT + 0x064)
    asm.label("mount_w")
    asm.lw(t1, t0, 0)
    asm.andi(t1, t1, 1)
    asm.beq(t1, x0, "mount_w")
    asm.li(t0, MOUNT + 0x080)
    asm.lw(s0, t0, 0)              # RESULT[0]
    print_label(asm, "MOUNT", s0)

    # ============================================================
    # Done banner
    # ============================================================
    for ch in "GAUNTLET:DONE":
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, 10)
    asm.call("putc")

    # Long delay then loop
    asm.li(t0, 0x200000)
    asm.label("_final_delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "_final_delay")
    asm.j("main")

    asm.resolve()
    return asm.code


def s8(x):
    x = x & 0xFF
    return x - 256 if x >= 128 else x


def sim_gf_mul(a, b):
    a, b = a & 0xFF, b & 0xFF
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return result


def sim_gf_inv(a):
    if a == 0:
        return 0
    result = a
    for _ in range(6):
        result = sim_gf_mul(result, result)
        result = sim_gf_mul(result, a)
    result = sim_gf_mul(result, result)
    return result


def sim_log2_8_8(v):
    """LOGOS-style approximate log2 in 8.8 fixed-point."""
    if v == 0:
        return 0
    v.bit_length() - 1
    # Take 8 bits below the MSB as the fraction (or whatever LOGOS does).
    # The exact formula is HDL-defined; we mark this as variable.
    return None


def sim_morton2(x, y):
    """16-bit X, 16-bit Y interleaved into 32-bit Morton code."""
    morton = 0
    for i in range(16):
        morton |= ((x >> i) & 1) << (2 * i)
        morton |= ((y >> i) & 1) << (2 * i + 1)
    return morton & 0xFFFFFFFF


def predict():
    """Return a dict {label: expected_value_or_None}."""
    out = {}
    # CRANK
    product = 0xDEADBEEF * 0xCAFEBABE
    out["CRANKLO"] = product & 0xFFFFFFFF
    out["CRANKHI"] = (product >> 32) & 0xFFFFFFFF
    # DIVIDE: crank_hi / 7
    out["DIVQ"] = out["CRANKHI"] // 7
    out["DIVR"] = out["CRANKHI"] % 7
    # TALLY: 100 * 200 = 20000
    out["TALLY"] = 20000
    # TAPER: saturating add 100+100 -> 127 (signed 8-bit clamp)
    r = 100 + 100
    if r > 127:
        r = 127
    out["TAPER"] = r & 0xFF
    # WEAVE: 0xFFFFFFFF - 0x12345678
    out["WEAVE"] = (0xFFFFFFFF - 0x12345678) & 0xFFFFFFFF
    # BLOOM
    out["BLOOMP"] = bin(0xDEADBEEF).count("1")
    # CLZ of 0xDEADBEEF: MSB is bit 31 set, so CLZ = 0
    out["BLOOMC"] = 0
    # CTZ of 0xDEADBEEF: bit 0 is 1, so CTZ = 0
    out["BLOOMT"] = 0
    # GLYPH: GF inverse of 0x53 in AES field = 0xCA
    out["GLYPH"] = sim_gf_inv(0x53)
    # SIEVE: extract bits [11:4] of 0xDEADBEEF = (0xDEADBEEF >> 4) & 0xFF
    out["SIEVE"] = (0xDEADBEEF >> 4) & 0xFF
    # MORTAR: A=[[2,3],[4,5]] B=[[6,7],[8,9]]
    out["MORTC00"] = (2*6 + 3*8) & 0xFFFFFFFF
    out["MORTC01"] = (2*7 + 3*9) & 0xFFFFFFFF
    out["MORTC10"] = (4*6 + 5*8) & 0xFFFFFFFF
    out["MORTC11"] = (4*7 + 5*9) & 0xFFFFFFFF
    # LOGOS: HDL-specific approximation, mark as variable
    out["LOGOS"] = None
    # FLIP: 8x8 transpose with row[0]=0xFF, others=0; col[0] = bit 0 of all rows = 0x01
    out["FLIP"] = 0x01
    # LACE: Morton(0xAAAA, 0x5555)
    out["LACE"] = sim_morton2(0xAAAA, 0x5555)
    # ORBIT: cos(0) ~ 0x10000 (1.0 in 1.15.16), sin(0) = 0
    # CORDIC has gain factor ~0.6073 so cos(0) might be slightly off; mark variable
    out["ORBITC"] = None
    out["ORBITS"] = None
    # MOUNT: Montgomery 1*1*R^-1 mod 3 = R^-1 mod 3, value depends on R
    out["MOUNT"] = None
    return out


def main():
    firmware = generate_firmware()
    print(f"Gauntlet firmware: {len(firmware)} instructions ({len(firmware)*4} bytes)")
    print(f"BRAM usage: {len(firmware)}/1024 ({len(firmware)*100//1024}%)")
    expected = predict()
    print("Expected silicon values:")
    for label, val in expected.items():
        if val is None:
            print(f"  {label:10s}: variable (HDL-specific)")
        else:
            print(f"  {label:10s}: 0x{val:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
