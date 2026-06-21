#!/usr/bin/env python3
"""Derive H(j) analytically for the INC-NOP ISA.
Closed form from cycle structure of INC on Z/256Z."""
from math import gcd, comb
from fractions import Fraction
import pandas as pd

N = 8
T_MAX = 256
n_ops = 5  # opcodes 0-4
# opcode 0 = INC, opcodes 1-4 = NOP

print("ANALYTICAL H(j) FOR ISA: INC NOP NOP NOP NOP JNZ")
print("=" * 60)
print()
print("INC acts as A <- (A+1) mod 256. NOP does nothing.")
print("A body of length k with m INC opcodes iterates A <- (A + m) mod 256.")
print("After t iterations: A = (t * m) mod 256.")
print("Halts when A = 0, i.e., t = 256 / gcd(m, 256).")
print("Steps consumed: t * (k + 1).")
print("Halts iff t * (k + 1) <= T_max = 256.")
print()

# Compute P(halt | JNZ at position k) analytically
print("P(halt | JNZ at position k):")
print()

p_halt_k = {}
for k in range(N):
    # Body: k opcodes from {0,1,2,3,4}. Opcode 0=INC (prob 1/5), rest=NOP (prob 4/5).
    # m = number of INC = number of opcode-0 occurrences in body.
    # m ~ Binomial(k, 1/5).

    total_halt = Fraction(0)

    if k == 0:
        # JNZ at position 0. A=0 from init. Falls through. Always halts.
        p_halt_k[k] = Fraction(1)
        print(f"  k=0: P(halt) = 1  (A=0 at JNZ, trivial)")
        continue

    for m in range(k + 1):
        # Probability of exactly m INC in k positions
        p_m = Fraction(comb(k, m), 5**k) * (4**(k - m))

        if m == 0:
            # No INC. A stays 0. Halts immediately.
            halts = True
        else:
            d = gcd(m, 256)
            t_needed = 256 // d
            steps = t_needed * (k + 1)
            halts = steps <= T_MAX

        if halts:
            total_halt += p_m

    p_halt_k[k] = total_halt
    print(f"  k={k}: P(halt) = {total_halt} = {float(total_halt):.6f}")

print()

# Compute H(1) as weighted average over JNZ positions
# For j=1: one JNZ at one of 8 positions, remaining 7 are non-JNZ.
# Each JNZ position k gives a body of length k.
# The tail (positions k+1..7) doesn't affect halting for the first JNZ.
# Weight of each k: (number of programs with JNZ at k and non-JNZ elsewhere)
# = 5^(k) * 1 * 5^(7-k) ... wait, the body opcodes matter for halt determination.
#
# H(1) = (1/total_1jnz_progs) * sum_k sum_{body} sum_{tail} I(halts)
# Since halting depends only on the body (not the tail), and tail has 5^(7-k) choices:
# H(1) = (1 / (8 * 5^7)) * sum_k 5^(7-k) * (number of halting bodies of length k)
# = (1 / 8) * sum_k P(halt | k)  [since body and tail contribute equally in weight]

# Actually: total programs with exactly 1 JNZ = 8 * 5^7 = 625000.
# For JNZ at position k: 5^k body choices, 5^(7-k) tail choices.
# 5^k * 5^(7-k) = 5^7 for each k. So each k contributes equally.
# H(1) = (1/8) * sum_{k=0}^{7} P(halt | k).

H1 = Fraction(0)
for k in range(N):
    H1 += p_halt_k[k]
H1 = H1 / N

print(f"H(1) = (1/8) * sum P(halt|k) = {H1} = {float(H1):.6f}")

# Verify against tensor
df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")
row = df[(df.op1==14)&(df.op2==14)&(df.op3==14)&(df.op4==14)]
if len(row):
    tensor_omega = row.iloc[0].omega
    print(f"Tensor Omega for this ISA: {tensor_omega:.6f}")

    # Predict Omega from H(0) and H(1)
    from math import comb as C
    w0 = Fraction(C(8,0) * 5**8, 6**8)
    w1 = Fraction(C(8,1) * 5**7, 6**8)
    omega_pred = w0 * 1 + w1 * H1
    # For j>=2, need H(2)...

    # Compute H(2) similarly
    # Programs with exactly 2 JNZ at positions k1 < k2.
    # The FIRST JNZ at k1 determines the loop body.
    # If the first loop halts (A reaches 0), execution continues past k1.
    # At k2, A might be nonzero again (from post-k1 opcodes).
    # This makes H(2) more complex.
    print(f"H(0)*w(0) + H(1)*w(1) = {float(omega_pred):.6f} (partial, j=0,1 only)")
    print(f"These two terms account for {float(w0+w1)*100:.1f}% of the total weight")

print()
print("CLOSED FORM:")
print()
print("For ISA = {INC, NOP, NOP, NOP, NOP, JNZ} with registers mod 256:")
print()
print("  P(halt | body length k) = sum_{m=0}^{k} C(k,m) * (1/5)^m * (4/5)^{k-m}")
print("                            * I(m=0 OR 256/gcd(m,256) * (k+1) <= 256)")
print()
print("  H(1) = (1/N) * sum_{k=0}^{N-1} P(halt | k)")
print()
print("  This is exact. It derives H(1) from the cycle structure of INC")
print("  on Z/256Z without enumerating any programs.")
