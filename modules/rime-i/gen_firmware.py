# ruff: noqa: F821, F841
#!/usr/bin/env python3
"""Generate RIME-I firmware: hand-assembled RV32I for test_math.

Computes Fibonacci(20), factorial(10), GCD(1071,462).
Prints results and PASS/FAIL to UART.
No multiply instruction — uses shift-and-add.
"""

class RV32I:
    def __init__(self):
        self.code = []
        self.labels = {}
        self.fixups = []

    def _emit(self, word):
        self.code.append(word)
        return len(self.code) - 1

    def label(self, name):
        self.labels[name] = len(self.code)

    def lui(self, rd, imm20):
        return self._emit(((imm20 & 0xFFFFF) << 12) | (rd << 7) | 0x37)

    def addi(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x13)

    def add(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x33)

    def sub(self, rd, rs1, rs2):
        return self._emit((0x20 << 25) | (rs2 << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x33)

    def sll(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (1 << 12) | (rd << 7) | 0x33)

    def srl(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (5 << 12) | (rd << 7) | 0x33)

    def sra(self, rd, rs1, rs2):
        return self._emit((0x20 << 25) | (rs2 << 20) | (rs1 << 15) | (5 << 12) | (rd << 7) | 0x33)

    def xor(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (4 << 12) | (rd << 7) | 0x33)

    def and_(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (7 << 12) | (rd << 7) | 0x33)

    def or_(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (6 << 12) | (rd << 7) | 0x33)

    def slli(self, rd, rs1, shamt):
        return self._emit((shamt << 20) | (rs1 << 15) | (1 << 12) | (rd << 7) | 0x13)

    def srli(self, rd, rs1, shamt):
        return self._emit((shamt << 20) | (rs1 << 15) | (5 << 12) | (rd << 7) | 0x13)

    def srai(self, rd, rs1, shamt):
        return self._emit(((0x400 | shamt) << 20) | (rs1 << 15) | (5 << 12) | (rd << 7) | 0x13)

    def andi(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (7 << 12) | (rd << 7) | 0x13)

    def xori(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (4 << 12) | (rd << 7) | 0x13)

    def ori(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (6 << 12) | (rd << 7) | 0x13)

    def slti(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x13)

    def sltiu(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (3 << 12) | (rd << 7) | 0x13)

    def sltu(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (3 << 12) | (rd << 7) | 0x33)

    def slt(self, rd, rs1, rs2):
        return self._emit((rs2 << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x33)

    def sw(self, rs2, rs1, imm12):
        imm_hi = (imm12 >> 5) & 0x7F
        imm_lo = imm12 & 0x1F
        return self._emit((imm_hi << 25) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | (imm_lo << 7) | 0x23)

    def sh(self, rs2, rs1, imm12):
        imm_hi = (imm12 >> 5) & 0x7F
        imm_lo = imm12 & 0x1F
        return self._emit((imm_hi << 25) | (rs2 << 20) | (rs1 << 15) | (1 << 12) | (imm_lo << 7) | 0x23)

    def sb(self, rs2, rs1, imm12):
        imm_hi = (imm12 >> 5) & 0x7F
        imm_lo = imm12 & 0x1F
        return self._emit((imm_hi << 25) | (rs2 << 20) | (rs1 << 15) | (0 << 12) | (imm_lo << 7) | 0x23)

    def lw(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x03)

    def lh(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (1 << 12) | (rd << 7) | 0x03)

    def lb(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x03)

    def lhu(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (5 << 12) | (rd << 7) | 0x03)

    def lbu(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (4 << 12) | (rd << 7) | 0x03)

    def auipc(self, rd, imm20):
        return self._emit(((imm20 & 0xFFFFF) << 12) | (rd << 7) | 0x17)

    def _branch(self, funct3, rs1, rs2, target_label):
        idx = self._emit(0)  # placeholder
        self.fixups.append((idx, funct3, rs1, rs2, target_label))
        return idx

    def beq(self, rs1, rs2, label): return self._branch(0, rs1, rs2, label)
    def bne(self, rs1, rs2, label): return self._branch(1, rs1, rs2, label)
    def blt(self, rs1, rs2, label): return self._branch(4, rs1, rs2, label)
    def bge(self, rs1, rs2, label): return self._branch(5, rs1, rs2, label)
    def bltu(self, rs1, rs2, label): return self._branch(6, rs1, rs2, label)
    def bgeu(self, rs1, rs2, label): return self._branch(7, rs1, rs2, label)

    def _jal(self, rd, target_label):
        idx = self._emit(0)
        self.fixups.append((idx, -1, rd, 0, target_label))
        return idx

    def jal(self, rd, label): return self._jal(rd, label)
    def j(self, label): return self._jal(0, label)
    def call(self, label): return self._jal(1, label)

    def jalr(self, rd, rs1, imm12):
        return self._emit(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x67)

    def ret(self):
        return self.jalr(0, 1, 0)

    def li(self, rd, value):
        """Load a 32-bit immediate into rd (may use 1 or 2 instructions)."""
        value = value & 0xFFFFFFFF
        if -2048 <= (value if value < 0x80000000 else value - 0x100000000) <= 2047:
            return self.addi(rd, 0, value & 0xFFF)
        upper = (value + 0x800) >> 12
        lower = value - (upper << 12)
        if lower >= 2048:
            lower -= 4096
            upper += 1
        self.lui(rd, upper & 0xFFFFF)
        if lower != 0:
            self.addi(rd, rd, lower & 0xFFF)

    def mv(self, rd, rs1):
        return self.addi(rd, rs1, 0)

    def nop(self):
        return self.addi(0, 0, 0)

    def fence(self):
        return self._emit(0x0000000F)

    def resolve(self):
        for idx, funct3, rs1_or_rd, rs2, target_label in self.fixups:
            target = self.labels[target_label]
            offset = (target - idx) * 4
            if funct3 == -1:  # JAL
                rd = rs1_or_rd
                imm = offset
                imm20 = (imm >> 20) & 1
                imm10_1 = (imm >> 1) & 0x3FF
                imm11 = (imm >> 11) & 1
                imm19_12 = (imm >> 12) & 0xFF
                self.code[idx] = (imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) | (imm19_12 << 12) | (rd << 7) | 0x6F
            else:  # Branch
                imm = offset
                imm12 = (imm >> 12) & 1
                imm10_5 = (imm >> 5) & 0x3F
                imm4_1 = (imm >> 1) & 0xF
                imm11 = (imm >> 11) & 1
                self.code[idx] = (imm12 << 31) | (imm10_5 << 25) | (rs2 << 20) | (rs1_or_rd << 15) | (funct3 << 12) | (imm4_1 << 8) | (imm11 << 7) | 0x63
        return self.code

    def hexdump(self):
        return '\n'.join(f'{w:08x}' for w in self.code)


# Register aliases
x0, ra, sp = 0, 1, 2
t0, t1, t2, t3, t4, t5 = 5, 6, 7, 28, 29, 30
a0, a1, a2, a3 = 10, 11, 12, 13
s0, s1, s2, s3, s4 = 8, 9, 18, 19, 20

UART_BASE = 0x20000


def generate_math_firmware(): pass
