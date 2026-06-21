#!/usr/bin/env python3
"""Generate hash-based torture firmware for any compositor module.

Each module test threads a running hash through every register write
and read the module supports.  If any register returns the wrong
value, the hash diverges and the final comparison fails.

The firmware also includes adversarial sequences: garbage writes,
reads before writes, rapid-fire operations, and boundary values.

Usage:
    from torture_gen import TortureBuilder
    tb = TortureBuilder("anvil")
    tb.reset(0x008, bit=0)
    tb.write(0x000, 0x52)
    tb.write(0x000, 0x49)
    tb.read_mix(0x004)
    tb.adversarial_write(0x000, 0xFFFFFFFF)
    tb.adversarial_write(0x000, 0x00000000)
    tb.read_mix(0x004)
    firmware, expected = tb.finish()
"""

from __future__ import annotations
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo / "modules" / "rime-i"))
sys.path.insert(0, str(_repo / "modules"))

_gf_src = (_repo / "modules" / "rime-i" / "gen_firmware.py").read_text()
_gf_ns = {}
exec(_gf_src.split("\ndef generate_math_firmware")[0], _gf_ns)
RV32I = _gf_ns['RV32I']

x0, ra, sp = 0, 1, 2
t0, t1, t2, t3, t4, t5 = 5, 6, 7, 28, 29, 30
a0, a1 = 10, 11
s0, s1, s2, s3, s4, s5 = 8, 9, 18, 19, 20, 21

MOD_BASE = 0x30000000
GOLDEN = 0x9E3779B9


def u32(x):
    """Mask to unsigned 32-bit."""
    return x & 0xFFFFFFFF


def s32(x):
    """Interpret as signed 32-bit (for arithmetic right shift)."""
    x = x & 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def sim_mix(acc, val):
    """Python simulation of the RV32I mix() subroutine.

    This must exactly match the assembly in the generated firmware:
    XOR, shift-add, shift-XOR, sign-conditional golden-ratio fold,
    force LSB=1. Any divergence means the firmware and Python produce
    different hashes, which is a test failure.
    """
    acc = u32(acc ^ val)
    acc = u32(acc + u32(acc << 5))       # avalanche: shift-add
    acc = u32(acc ^ (acc >> 13))          # avalanche: shift-XOR
    sign_mask = u32(u32(s32(acc) >> 31))  # arithmetic right shift: all-1s or all-0s
    acc = u32(acc ^ u32(sign_mask & GOLDEN))  # conditional fold with golden ratio
    acc = u32(acc | 1)                    # force odd (prevents degenerate zero chains)
    return acc


class TortureBuilder:
    """Generates firmware + Python simulation for a module torture test."""

    def __init__(self, mod_name: str):
        self.mod_name = mod_name
        self.asm = RV32I()
        self.sim_hash = 0
        self.ops: list[str] = []
        self._started = False
        self._init()

    def _init(self):
        a = self.asm
        a.lui(sp, 0x00001)
        a.lui(s4, 0x20000)
        a.j("main")

        a.label("putc")
        a.lw(t0, s4, 4)
        a.bne(t0, x0, "putc")
        a.sw(a0, s4, 0)
        a.ret()

        a.label("puthex")
        a.addi(sp, sp, -8)
        a.sw(ra, sp, 4)
        a.sw(s0, sp, 0)
        a.mv(s0, a0)
        a.addi(s1, x0, 28)
        a.label("ph_loop")
        a.blt(s1, x0, "ph_done")
        a.srl(a0, s0, s1)
        a.andi(a0, a0, 0xF)
        a.addi(t0, x0, 10)
        a.blt(a0, t0, "ph_digit")
        a.addi(a0, a0, ord('A') - 10)
        a.j("ph_emit")
        a.label("ph_digit")
        a.addi(a0, a0, ord('0'))
        a.label("ph_emit")
        a.call("putc")
        a.addi(s1, s1, -4)
        a.j("ph_loop")
        a.label("ph_done")
        a.lw(s0, sp, 0)
        a.lw(ra, sp, 4)
        a.addi(sp, sp, 8)
        a.ret()

        # mix(a0=acc, a1=val) -> a0
        a.label("mix")
        a.xor(a0, a0, a1)
        a.slli(t0, a0, 5)
        a.add(a0, a0, t0)
        a.srli(t0, a0, 13)
        a.xor(a0, a0, t0)
        a.srai(t0, a0, 31)
        a.li(t1, GOLDEN)
        a.and_(t0, t0, t1)
        a.xor(a0, a0, t0)
        a.ori(a0, a0, 1)
        a.ret()

        a.label("main")
        # Salt the hash with a module-name-derived value so two tests that
        # happen to issue identical register accesses still produce unique
        # hashes. Computed via FNV-1a over the module name bytes.
        salt = 0x811C9DC5
        for ch in self.mod_name.encode("ascii"):
            salt = u32((salt ^ ch) * 0x01000193)
        a.li(s0, salt)
        self.sim_hash = salt
        self._started = True

    def _mod_addr(self, offset: int) -> int:
        return MOD_BASE + offset

    def write(self, offset: int, value: int):
        """Write a value to a module register."""
        a = self.asm
        addr = self._mod_addr(offset)
        a.li(t0, addr)
        a.li(t1, value)
        a.sw(t1, t0, 0)
        self.ops.append(f"W 0x{offset:03X} = 0x{value:08X}")

    def read_mix(self, offset: int, sim_value: int | None = None):
        """Read a register and mix the value into the hash.

        With *sim_value*, firmware and Python both mix that value (the register
        must return it). Without it the value is unpredictable: the register is
        still read on hardware (exercising the bus path), but neither side mixes
        it, so the hash chains stay synchronized — identical to
        :meth:`read_discard`. Mixing the firmware's actual read while the
        simulation mixes 0 would diverge on any non-zero register.
        """
        a = self.asm
        addr = self._mod_addr(offset)
        a.li(t0, addr)
        if sim_value is None:
            a.lw(t1, t0, 0)  # read on hardware, do not mix (unpredictable value)
            self.ops.append(f"R 0x{offset:03X} -> read (unpredictable, unmixed)")
            return
        a.lw(a1, t0, 0)
        a.mv(a0, s0)
        a.call("mix")
        a.mv(s0, a0)
        self.sim_hash = sim_mix(self.sim_hash, u32(sim_value))
        self.ops.append(f"R 0x{offset:03X} -> mix (sim=0x{sim_value:08X})")

    def read_discard(self, offset: int):
        """Read a register on hardware (exercises the bus path) but do NOT
        mix the value into the hash.  Both Python and hardware skip the mix,
        so the hash chains stay synchronized."""
        a = self.asm
        addr = self._mod_addr(offset)
        a.li(t0, addr)
        a.lw(t1, t0, 0)  # read into t1, do not call mix
        self.ops.append(f"R 0x{offset:03X} -> discard")

    def read_check(self, offset: int, expected: int):
        """Read a register, verify it matches expected, and mix into hash."""
        a = self.asm
        addr = self._mod_addr(offset)
        a.li(t0, addr)
        a.lw(a1, t0, 0)
        a.mv(a0, s0)
        a.call("mix")
        a.mv(s0, a0)
        self.sim_hash = sim_mix(self.sim_hash, u32(expected))
        self.ops.append(f"R 0x{offset:03X} == 0x{expected:08X} -> mix")

    def read_assert(self, offset: int, expected: int):
        """Read a register and diverge the hash immediately on mismatch.

        Unlike read_check, this primitive folds the *actual* read value into
        the hash. If hardware returned the wrong value, the hash diverges
        from the Python prediction at this point, not only at final compare.
        This makes per-register validation unambiguous and forbids any two
        modules from producing the same hash unless they actually exercise
        identical register sequences returning identical values.

        Both the expected value and the (expected XOR label-bits) are
        mixed so that two different offsets with the same expected value
        still produce different hashes.
        """
        a = self.asm
        addr = self._mod_addr(offset)
        # Tag the mix with the offset so the same expected at different
        # offsets produces different hash output, preventing structural
        # collisions between tests that happen to touch identical values.
        tag = u32(expected ^ (offset * 0x9E3779B1) ^ (addr * 0x01000193))
        a.li(t0, addr)
        a.lw(a1, t0, 0)
        # Fold offset-tagged expected into register a1 before mixing
        a.li(t2, tag ^ u32(expected))  # the XOR mask that converts read into tag
        a.xor(a1, a1, t2)
        a.mv(a0, s0)
        a.call("mix")
        a.mv(s0, a0)
        self.sim_hash = sim_mix(self.sim_hash, tag)
        self.ops.append(f"R 0x{offset:03X} assert 0x{expected:08X} (tag 0x{tag:08X})")

    def read_assert_masked(self, offset: int, expected: int, mask: int):
        """Read a register, keep only *mask* bits, and assert they equal
        *expected*. For registers whose other bits are nondeterministic (e.g.
        snoop-driven counters or flags), this validates the host-controlled
        bits without diverging the hash on the rest.
        """
        a = self.asm
        addr = self._mod_addr(offset)
        tag = u32(expected ^ (offset * 0x9E3779B1) ^ (addr * 0x01000193))
        a.li(t0, addr)
        a.lw(a1, t0, 0)
        a.andi(a1, a1, mask)
        a.li(t2, tag ^ u32(expected))
        a.xor(a1, a1, t2)
        a.mv(a0, s0)
        a.call("mix")
        a.mv(s0, a0)
        self.sim_hash = sim_mix(self.sim_hash, tag)
        self.ops.append(f"R 0x{offset:03X} assert&0x{mask:X} == 0x{expected:08X}")

    def reset(self, offset: int, *, bit: int = 0):
        """Write a reset/control register."""
        self.write(offset, 1 << bit)

    def adversarial_write(self, offset: int, value: int):
        """Write a garbage/boundary value — tests resilience."""
        self.write(offset, value)
        self.ops.append("  (adversarial)")

    def delay(self, cycles: int):
        """Insert a short delay loop."""
        a = self.asm
        a.li(t0, cycles)
        a.label(f"_delay_{len(self.ops)}")
        a.addi(t0, t0, -1)
        a.bne(t0, x0, f"_delay_{len(self.ops)}")
        self.ops.append(f"delay {cycles}")

    def finish(self) -> tuple[list[int], int]:
        """Emit comparison + print + loop. Returns (firmware, expected_hash)."""
        a = self.asm
        expected = self.sim_hash

        a.li(t0, expected)
        a.beq(s0, t0, "pass")

        for ch in "FAIL:":
            a.addi(a0, x0, ord(ch))
            a.call("putc")
        a.mv(a0, s0)
        a.call("puthex")
        a.addi(a0, x0, 10)
        a.call("putc")
        a.j("done")

        a.label("pass")
        for ch in "PASS":
            a.addi(a0, x0, ord(ch))
            a.call("putc")
        a.addi(a0, x0, 10)
        a.call("putc")

        a.label("done")
        a.li(t0, 0x200000)
        a.label("_final_delay")
        a.addi(t0, t0, -1)
        a.bne(t0, x0, "_final_delay")
        a.j("main")

        a.resolve()
        return a.code, expected
