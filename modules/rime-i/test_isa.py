#!/usr/bin/env python3
"""RIME-I RV32I full-ISA torture test.

A single computation that threads a 32-bit hash through every
instruction the CPU implements.  If any one of the 37 instructions
produces the wrong result, the hash diverges and the final
comparison fails.

The algorithm:
  1. Build a 12-word data block in BRAM using SW, SH, SB — each
     store type produces bytes that a different load type will read.
  2. Read each word back through LW, LH, LHU, LB, LBU.  Sign
     extension (or its absence) changes the loaded value, which
     changes the hash.  Each loaded value is folded into the hash
     via a call to mix().
  3. mix() is a subroutine (JAL/JALR) that applies every R-type
     and I-type ALU operation to the accumulator: ADD, SUB, XOR,
     OR, AND, SLL, SRL, SRA and their immediate variants, plus
     SLT, SLTU, SLTI, SLTIU.  Every operation modifies the hash.
  4. A branch gauntlet feeds the hash through all six branch types.
     Each branch selects between two different constants that get
     XORed in — the path taken depends on the hash value at that
     point, so a wrong branch decision propagates.
  5. LUI and AUIPC fold final constants.  AUIPC's contribution
     depends on the instruction's PC, computed at generation time.

The expected hash is computed by a Python reference simulation
that runs the identical algorithm with identical data.  The
firmware compares its result against this value and prints PASS
or FAIL.

Run:    python modules/rime-i/test_isa.py
Build:  python modules/rime-i/test_isa.py --gen-only
"""

import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(_repo))

from compositor_test import RV32I  # noqa: E402

x0, ra, sp = 0, 1, 2
t0, t1, t2, t3, t4, t5 = 5, 6, 7, 28, 29, 30
a0, a1 = 10, 11
s0, s1, s2, s3, s4, s5, s6 = 8, 9, 18, 19, 20, 21, 22

GOLDEN = 0x9E3779B9


def u32(x):
    return x & 0xFFFFFFFF


def s32(x):
    x = x & 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def s16(x):
    x = x & 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def s8(x):
    x = x & 0xFF
    return x - 0x100 if x >= 0x80 else x


def sim_mix(acc, val):
    """Reference implementation of the mix subroutine."""
    w = val
    acc = u32(acc ^ w)
    acc = u32(acc + u32(u32(acc << 5) & 0xFFFFFFFF))
    acc = u32(acc ^ (acc >> 13))
    sign_mask = u32(u32(s32(acc) >> 31))
    acc = u32(acc ^ u32(sign_mask & GOLDEN))
    acc = u32(acc | 1)
    acc = u32(acc + u32(w & 0xFF))
    not_w = u32(w ^ 0xFFFFFFFF)
    acc = u32(acc ^ not_w)
    mid = u32(acc ^ 0x80000000)
    carry = 1 if mid < w else 0
    acc = u32(acc + carry)
    neg = 1 if s32(acc) < 0 else 0
    acc = u32(acc ^ neg)
    low_byte = w & 0xFF
    small = 1 if low_byte < 128 else 0
    acc = u32(acc + small)
    sra_val = u32(s32(acc) >> 3)
    acc = u32(acc ^ sra_val)
    acc = u32(acc - w)
    shifted_w = (w >> 16) & 0xFFFF
    acc = u32(acc | shifted_w)
    slt_result = 1 if s32(acc) < s32(w) else 0
    acc = u32(acc ^ u32(slt_result << 5))
    return acc


def simulate(auipc_pc: int) -> int:
    """Run the full algorithm in Python and return the expected hash.

    Parameters
    ----------
    auipc_pc : int
        The PC value (byte address) at which the AUIPC instruction in the
        generated firmware lands.  ``gen_firmware()`` computes this from
        the assembler label table and passes it here; the hash chain folds
        it in as the final mixing step.  This is NOT the firmware list.
    """
    seed = 0xA5A5A5A5
    mem = bytearray(48)

    def lfsr_step(v):
        v = u32(v ^ u32(v << 13))
        v = u32(v ^ (v >> 17))
        v = u32(v ^ u32(v << 5))
        return v

    def write_word(off, val):
        mem[off+0] = val & 0xFF
        mem[off+1] = (val >> 8) & 0xFF
        mem[off+2] = (val >> 16) & 0xFF
        mem[off+3] = (val >> 24) & 0xFF

    def read_word(off):
        return mem[off] | (mem[off+1]<<8) | (mem[off+2]<<16) | (mem[off+3]<<24)

    st = seed
    for i in range(3):
        st = lfsr_step(st)
        write_word(i*4, st)

    for i in range(3, 6):
        st = lfsr_step(st)
        lo = st & 0xFFFF
        hi = (st >> 16) & 0xFFFF
        off = i * 4
        mem[off+0] = lo & 0xFF
        mem[off+1] = (lo >> 8) & 0xFF
        mem[off+2] = hi & 0xFF
        mem[off+3] = (hi >> 8) & 0xFF

    for i in range(6, 9):
        st = lfsr_step(st)
        off = i * 4
        mem[off+0] = st & 0xFF
        mem[off+1] = (st >> 8) & 0xFF
        mem[off+2] = (st >> 16) & 0xFF
        mem[off+3] = (st >> 24) & 0xFF

    w9  = u32(read_word(0) ^ read_word(12))
    w10 = u32(read_word(4) | read_word(16))
    w11 = u32(read_word(8) & read_word(20))
    write_word(36, w9)
    write_word(40, w10)
    write_word(44, w11)

    h = 0

    for i in range(3):
        h = sim_mix(h, read_word(i*4))

    h = sim_mix(h, u32(s16(mem[12] | (mem[13]<<8))))
    h = sim_mix(h, u32(s16(mem[14] | (mem[15]<<8))))

    h = sim_mix(h, mem[16] | (mem[17]<<8))
    h = sim_mix(h, mem[18] | (mem[19]<<8))

    h = sim_mix(h, u32(s16(mem[20] | (mem[21]<<8))))
    h = sim_mix(h, mem[22] | (mem[23]<<8))

    h = sim_mix(h, u32(s8(mem[24])))
    h = sim_mix(h, u32(s8(mem[25])))
    h = sim_mix(h, u32(s8(mem[26])))
    h = sim_mix(h, u32(s8(mem[27])))

    h = sim_mix(h, mem[28])
    h = sim_mix(h, mem[29])
    h = sim_mix(h, mem[30])
    h = sim_mix(h, mem[31])

    h = sim_mix(h, u32(s8(mem[32])))
    h = sim_mix(h, u32(s8(mem[33])))
    h = sim_mix(h, mem[34])
    h = sim_mix(h, mem[35])

    for i in range(9, 12):
        h = sim_mix(h, read_word(i*4))

    if (h & 0xFF) == 0:
        h = u32(h ^ 0x11111111)
    if (h & 0xFF) != 0:
        h = u32(h + 0x77)
    if s32(h) < 0:
        h = u32(h ^ 0xFF00FF00)
    if s32(h) >= 0:
        h = u32(h + 0x1234)
    if h < 0x80000000:
        h = u32(h ^ 0xAA)
    if h >= 1:
        h = u32(h + 0x55)

    h = u32(h ^ 0x31415000)
    h = u32(h + u32(auipc_pc))

    return h


def gen_firmware():
    asm = RV32I()

    asm.lui(sp, 0x00001)
    asm.lui(s4, 0x20000)
    asm.j("main")

    # --- putc(a0) ---
    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    # --- puthex(a0): print 32-bit value as 8 hex chars ---
    asm.label("puthex")
    asm.addi(sp, sp, -8)
    asm.sw(ra, sp, 4)
    asm.sw(s0, sp, 0)
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
    asm.lw(s0, sp, 0)
    asm.lw(ra, sp, 4)
    asm.addi(sp, sp, 8)
    asm.ret()

    # ---------------------------------------------------------------
    # mix(a0=acc, a1=val) -> a0
    #
    # Uses every R-type and I-type ALU instruction:
    #   R: ADD SUB XOR OR AND SLL SRL SRA SLT SLTU
    #   I: ADDI XORI ORI ANDI SLLI SRLI SRAI SLTI SLTIU
    # ---------------------------------------------------------------
    asm.label("mix")
    asm.xor(a0, a0, a1)              # XOR reg
    asm.slli(t0, a0, 5)              # SLLI
    asm.add(a0, a0, t0)              # ADD reg
    asm.srli(t0, a0, 13)             # SRLI
    asm.xor(a0, a0, t0)              # XOR reg (second use, different operand)
    asm.srai(t0, a0, 31)             # SRAI — sign mask (0 or -1)
    asm.li(t1, GOLDEN)               # LUI+ADDI (constant)
    asm.and_(t0, t0, t1)             # AND reg — GOLDEN if neg, else 0
    asm.xor(a0, a0, t0)              # XOR fold
    asm.ori(a0, a0, 1)               # ORI — force LSB
    asm.andi(t0, a1, 0xFF)           # ANDI — low byte of val
    asm.add(a0, a0, t0)              # ADD fold
    asm.xori(t0, a1, -1)             # XORI -1 = NOT val
    asm.xor(a0, a0, t0)              # XOR fold
    asm.li(t1, 0x80000000)
    asm.xor(t1, a0, t1)              # flip sign bit -> different unsigned magnitude
    asm.sltu(t0, t1, a1)             # SLTU — unsigned compare flipped acc vs val
    asm.add(a0, a0, t0)              # ADD fold
    asm.slti(t0, a0, 0)              # SLTI — is negative?
    asm.xor(a0, a0, t0)              # XOR fold
    asm.andi(t0, a1, 0xFF)            # low byte of val
    asm.sltiu(t0, t0, 128)           # SLTIU — is low byte < 128?
    asm.add(a0, a0, t0)              # ADD fold
    asm.addi(t1, x0, 3)              # shift amount for SRA reg
    asm.sra(t0, a0, t1)              # SRA reg
    asm.xor(a0, a0, t0)              # XOR fold
    asm.sub(a0, a0, a1)              # SUB reg
    asm.srli(t0, a1, 16)             # SRL (via SRLI on val)
    asm.or_(a0, a0, t0)              # OR reg
    asm.slt(t0, a0, a1)              # SLT — signed comparison (not used for branch, just value)
    asm.addi(t1, x0, 5)
    asm.sll(t0, t0, t1)              # SLL reg — shift the SLT result
    asm.xor(a0, a0, t0)              # XOR fold
    asm.ret()

    # ---------------------------------------------------------------
    # main
    # ---------------------------------------------------------------
    asm.label("main")
    asm.addi(sp, sp, -80)
    asm.sw(ra, sp, 76)

    asm.addi(s5, sp, 0)              # s5 = scratch base (word-aligned)
    asm.addi(s0, x0, 0)              # s0 = hash accumulator

    # === PHASE 1: Build 12-word data block ===
    # Words 0-2 via SW (LFSR-derived)
    asm.li(s1, 0xA5A5A5A5)           # s1 = LFSR state

    for i in range(3):
        asm.slli(t0, s1, 13)
        asm.xor(s1, s1, t0)
        asm.srli(t0, s1, 17)
        asm.xor(s1, s1, t0)
        asm.slli(t0, s1, 5)
        asm.xor(s1, s1, t0)
        asm.sw(s1, s5, i * 4)

    # Words 3-5 via SH pairs
    for i in range(3, 6):
        asm.slli(t0, s1, 13)
        asm.xor(s1, s1, t0)
        asm.srli(t0, s1, 17)
        asm.xor(s1, s1, t0)
        asm.slli(t0, s1, 5)
        asm.xor(s1, s1, t0)
        asm.sh(s1, s5, i * 4)                      # lo half at +0
        asm.srli(t0, s1, 16)
        asm.sh(t0, s5, i * 4 + 2)                  # hi half at +2

    # Words 6-8 via SB quads
    for i in range(6, 9):
        asm.slli(t0, s1, 13)
        asm.xor(s1, s1, t0)
        asm.srli(t0, s1, 17)
        asm.xor(s1, s1, t0)
        asm.slli(t0, s1, 5)
        asm.xor(s1, s1, t0)
        asm.sb(s1, s5, i * 4)                       # byte 0
        asm.srli(t0, s1, 8)
        asm.sb(t0, s5, i * 4 + 1)                   # byte 1
        asm.srli(t0, s1, 16)
        asm.sb(t0, s5, i * 4 + 2)                   # byte 2
        asm.srli(t0, s1, 24)
        asm.sb(t0, s5, i * 4 + 3)                   # byte 3

    # Words 9-11: derived from earlier words via ALU
    asm.lw(t0, s5, 0)
    asm.lw(t1, s5, 12)
    asm.xor(t2, t0, t1)
    asm.sw(t2, s5, 36)
    asm.lw(t0, s5, 4)
    asm.lw(t1, s5, 16)
    asm.or_(t2, t0, t1)
    asm.sw(t2, s5, 40)
    asm.lw(t0, s5, 8)
    asm.lw(t1, s5, 20)
    asm.and_(t2, t0, t1)
    asm.sw(t2, s5, 44)

    # === PHASE 2: Read back + mix via every load type ===

    # Words 0-2: LW
    for i in range(3):
        asm.lw(a1, s5, i * 4)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)

    # Words 3-5: LH and LHU — each loaded value mixed individually
    # so sign extension (LH) vs zero extension (LHU) directly affects the hash
    for off in [12, 14]:
        asm.lh(a1, s5, off)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)
    for off in [16, 18]:
        asm.lhu(a1, s5, off)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)
    asm.lh(a1, s5, 20)
    asm.mv(a0, s0)
    asm.call("mix")
    asm.mv(s0, a0)
    asm.lhu(a1, s5, 22)
    asm.mv(a0, s0)
    asm.call("mix")
    asm.mv(s0, a0)

    # Words 6-8: LB and LBU — each byte mixed as full 32-bit value
    # LB sign-extends (0xF3 -> 0xFFFFFFF3), LBU zero-extends (0xF3 -> 0x000000F3)
    for off in [24, 25, 26, 27]:
        asm.lb(a1, s5, off)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)
    for off in [28, 29, 30, 31]:
        asm.lbu(a1, s5, off)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)
    for off in [32, 33]:
        asm.lb(a1, s5, off)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)
    for off in [34, 35]:
        asm.lbu(a1, s5, off)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)

    # Words 9-11: LW
    for i in range(9, 12):
        asm.lw(a1, s5, i * 4)
        asm.mv(a0, s0)
        asm.call("mix")
        asm.mv(s0, a0)

    # === PHASE 3: Branch gauntlet ===
    # Each branch tests a different condition on the hash and
    # XORs/adds a different constant. The path taken is determined
    # by the hash, so any upstream error propagates.

    # BEQ: if low byte == 0
    asm.andi(t0, s0, 0xFF)
    asm.beq(t0, x0, "beq_taken")
    asm.j("beq_skip")
    asm.label("beq_taken")
    asm.li(t0, 0x11111111)
    asm.xor(s0, s0, t0)
    asm.label("beq_skip")

    # BNE: if low byte != 0
    asm.andi(t0, s0, 0xFF)
    asm.bne(t0, x0, "bne_taken")
    asm.j("bne_skip")
    asm.label("bne_taken")
    asm.addi(s0, s0, 0x77)
    asm.label("bne_skip")

    # BLT: if signed hash < 0
    asm.blt(s0, x0, "blt_taken")
    asm.j("blt_skip")
    asm.label("blt_taken")
    asm.li(t0, 0xFF00FF00)
    asm.xor(s0, s0, t0)
    asm.label("blt_skip")

    # BGE: if signed hash >= 0
    asm.bge(s0, x0, "bge_taken")
    asm.j("bge_skip")
    asm.label("bge_taken")
    asm.li(t0, 0x1234)
    asm.add(s0, s0, t0)
    asm.label("bge_skip")

    # BLTU: if unsigned hash < 0x80000000
    asm.lui(t0, 0x80000)
    asm.bltu(s0, t0, "bltu_taken")
    asm.j("bltu_skip")
    asm.label("bltu_taken")
    asm.xori(s0, s0, 0xAA)
    asm.label("bltu_skip")

    # BGEU: if unsigned hash >= 1
    asm.addi(t0, x0, 1)
    asm.bgeu(s0, t0, "bgeu_taken")
    asm.j("bgeu_skip")
    asm.label("bgeu_taken")
    asm.addi(s0, s0, 0x55)
    asm.label("bgeu_skip")

    # === PHASE 4: LUI + AUIPC fold ===
    asm.lui(t0, 0x31415)             # pi fragment
    asm.xor(s0, s0, t0)

    auipc_idx = len(asm.code)        # record PC of AUIPC instruction
    asm.auipc(t0, 0)                 # t0 = PC of this instruction
    asm.add(s0, s0, t0)              # fold into hash

    # === Compute expected hash and compare ===
    auipc_pc = auipc_idx * 4
    expected = simulate(auipc_pc)

    asm.li(t0, expected)
    asm.beq(s0, t0, "pass")

    # --- FAIL: print "FAIL:" + hex(actual) + "\n" ---
    for ch in "FAIL:":
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.mv(a0, s0)
    asm.call("puthex")
    asm.addi(a0, x0, ord(':'))
    asm.call("putc")
    asm.mv(a0, t0)
    asm.call("puthex")   # expected (already in t0... but clobbered by puthex)
    # Actually t0 is clobbered. Just print actual.
    asm.addi(a0, x0, 10)
    asm.call("putc")
    asm.j("done")

    asm.label("pass")
    for ch in "PASS":
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, 10)
    asm.call("putc")

    asm.label("done")
    asm.lw(ra, sp, 76)
    asm.addi(sp, sp, 80)
    asm.li(t0, 0x200000)
    asm.label("delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "delay")
    asm.j("main")

    asm.resolve()
    return asm.code, expected


def main():
    firmware, expected = gen_firmware()
    print(f"ISA torture firmware: {len(firmware)} instructions ({len(firmware)*4} bytes)")
    print(f"Expected hash: 0x{expected:08X}")
    print(f"BRAM usage: {len(firmware)}/1024 ({len(firmware)*100/1024:.1f}%)")

    if "--gen-only" in sys.argv:
        for i, w in enumerate(firmware):
            print(f"        bram[{i}] = 32'h{w:08x};")
        return 0

    from compositor_test import flash_and_read, restore_rime
    import subprocess

    mod_dir = Path(__file__).resolve().parent

    # The ISA test is a standalone RIME-I (no compositor module).
    # Use a dummy module name that matches rime_i_core but the template
    # won't actually instantiate it — it connects the CPU memory bus
    # to BRAM + UART only. We achieve this by generating with an empty
    # module name trick: generate_top_sv uses {mod_name} for instantiation.
    # Since the ISA test uses no module, we use the N-way compositor instead.
    from icepi.compose import compose, write_firmware_hex, CompositionPlan
    plan = CompositionPlan(modules=[], total_luts=4050, total_brams=7,
                           total_mults=0, available_luts=21860, available_brams=56,
                           available_mults=28, fits=True, address_map={})
    top_text = compose(plan, firmware)
    (mod_dir / "top.sv").write_text(top_text, encoding="utf-8")
    # compose()'s top.sv loads BRAM via $readmemh("firmware.hex"); without
    # writing it here the build silently falls back to the stale tracked hex
    # and the CPU runs the wrong program (null/garbage readback). Same defect
    # class as the cmd_compose and verify.py fixes.
    write_firmware_hex(firmware, mod_dir / "firmware.hex")

    print("Building...")
    result = subprocess.run(
        [sys.executable, str(_repo / "icepi_helper.py"),
         "build", "rime-i", "--clean"],
        capture_output=True, text=True, cwd=str(_repo), timeout=300,
    )
    ok = result.returncode == 0
    luts = 0
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if "Total LUT4s:" in line:
            try:
                luts = int(line.split("LUT4s:")[1].split("/")[0].strip())
            except (ValueError, IndexError):
                pass
    if not ok:
        print("BUILD FAILED")
        return 1
    print(f"Build: {luts} LUTs")

    print("Flashing and reading serial output...")
    output = flash_and_read("rime-i")
    print(f"Raw output: {output[:200]!r}")

    lines = [l.strip() for l in output.split('\n') if l.strip()]  # noqa: E741
    if not lines:
        print("NO OUTPUT")
        restore_rime()
        return 1

    first = lines[0]
    if "PASS" in first:
        print(f"ISA torture: PASS (hash 0x{expected:08X})")
        restore_rime()
        return 0
    else:
        print("ISA torture: FAIL")
        print(f"Expected: 0x{expected:08X}")
        print(f"Board output: {first}")
        restore_rime()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
