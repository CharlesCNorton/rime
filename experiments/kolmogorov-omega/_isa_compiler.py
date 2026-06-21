#!/usr/bin/env python3
"""ISA compiler: given a target output specification, find the ISA that best matches.

Inverts the paper's question: instead of "given ISA, what does it produce?"
answer "given what I want, which ISA produces it?"

Targets:
  1. Uniform: P(x) = 1/256 for all x (maximum entropy)
  2. Peaked: P(0) > 0.9 (concentrate on output 0)
  3. Top-k: maximize number of reachable outputs
  4. Custom: arbitrary target distribution
"""
import numpy as np
import pandas as pd
import json

data = np.load("experiments/kolmogorov-omega/output_tensor.npz")
hist = data["hist"]
halting = data["halting"]
ops = data["ops"]

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")
n_isas = len(hist)

OP_NAMES = {0:'INC',1:'DEC',2:'SWP',3:'ADD',4:'XOR',6:'NEG',7:'MOV',
            8:'SUB',9:'AND',10:'OR',11:'SHR',12:'SHL',13:'CPL',14:'NOP'}

P = hist.astype(np.float64)
for i in range(n_isas):
    if halting[i] > 0:
        P[i] /= halting[i]

def kl_divergence(p, q):
    kl = 0.0
    for x in range(256):
        if p[x] > 0 and q[x] > 0:
            kl += p[x] * np.log2(p[x] / q[x])
        elif p[x] > 0:
            kl += 20.0
    return kl

def isa_label(i):
    o = ops[i]
    names = [OP_NAMES.get(int(o[j]), '?') for j in range(4)]
    return f"INC {names[0]} {names[1]} {names[2]} {names[3]} JNZ"

def find_best(target, name, top_n=10):
    print(f"\n=== TARGET: {name} ===")
    scores = np.zeros(n_isas)
    for i in range(n_isas):
        if halting[i] == 0:
            scores[i] = 1e9
            continue
        scores[i] = kl_divergence(target, P[i])
    best = np.argsort(scores)[:top_n]
    print(f"{'Rank':<5} {'KL':>8} {'Omega':>8} {'Entropy':>8} {'Reach':>6}  ISA")
    print("-" * 60)
    for rank, idx in enumerate(best):
        o = ops[idx]
        omega = halting[idx] / 1679616
        p_nz = P[idx][P[idx] > 0]
        entropy = -np.sum(p_nz * np.log2(p_nz)) if len(p_nz) > 0 else 0
        reach = int(np.sum(P[idx] > 0))
        print(f"{rank+1:<5} {scores[idx]:>8.4f} {omega:>8.4f} {entropy:>8.2f} {reach:>6}  {isa_label(idx)}")
    return [(int(best[i]), float(scores[best[i]])) for i in range(top_n)]

print("=== ISA COMPILER ===")
print(f"Searching {n_isas} ISAs for optimal match to target specifications.\n")

uniform = np.ones(256) / 256
r1 = find_best(uniform, "UNIFORM (max entropy)")

peaked = np.zeros(256)
peaked[0] = 0.95
peaked[1] = 0.03
peaked[2] = 0.02
r2 = find_best(peaked, "PEAKED at output 0 (P(0)=0.95)")

broad = np.ones(256) / 256
r3_scores = np.array([int(np.sum(P[i] > 0)) for i in range(n_isas)])
print(f"\n=== TARGET: MAXIMUM REACHABLE OUTPUTS ===")
best_reach = np.argsort(r3_scores)[::-1][:10]
print(f"{'Rank':<5} {'Reach':>6} {'Omega':>8} {'Entropy':>8}  ISA")
print("-" * 50)
for rank, idx in enumerate(best_reach):
    omega = halting[idx] / 1679616
    p_nz = P[idx][P[idx] > 0]
    entropy = -np.sum(p_nz * np.log2(p_nz)) if len(p_nz) > 0 else 0
    print(f"{rank+1:<5} {r3_scores[idx]:>6} {omega:>8.4f} {entropy:>8.2f}  {isa_label(idx)}")

balanced = np.zeros(256)
for x in range(16):
    balanced[x] = 1.0 / 16
r4 = find_best(balanced, "BALANCED over outputs 0-15")

low_x = np.zeros(256)
for x in [0, 1, 255]:
    low_x[x] = 1.0 / 3
r5 = find_best(low_x, "TRIPLE: equal weight on 0, 1, 255")

results = {
    "uniform_best": r1[:3],
    "peaked_best": r2[:3],
    "max_reachable": [(int(best_reach[i]), int(r3_scores[best_reach[i]])) for i in range(3)],
    "balanced_best": r4[:3],
    "triple_best": r5[:3],
}
with open("experiments/kolmogorov-omega/isa_compiler.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nWrote isa_compiler.json")
