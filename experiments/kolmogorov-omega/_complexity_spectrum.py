#!/usr/bin/env python3
"""Kolmogorov complexity spectrum + I(ISA; output) + output convergence."""
import numpy as np
import pandas as pd
import numba
import time

print("=== PART 1: COMPLEXITY SPECTRUM (Gini of K distribution) ===", flush=True)

data = np.load("experiments/kolmogorov-omega/output_tensor.npz")
hist = data["hist"]
k_prog = data["k_prog"]
halting = data["halting"]
ops = data["ops"]

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")

n_isas = len(hist)

gini_values = np.zeros(n_isas)
for i in range(n_isas):
    kp = k_prog[i]
    valid = kp[kp >= 0]
    if len(valid) < 2:
        gini_values[i] = 0
        continue
    sorted_k = np.sort(valid)
    n = len(sorted_k)
    index = np.arange(1, n + 1)
    gini_values[i] = (2 * np.sum(index * sorted_k) - (n + 1) * np.sum(sorted_k)) / (n * np.sum(sorted_k)) if np.sum(sorted_k) > 0 else 0

print(f"Gini coefficient of K(x) distribution across {n_isas} ISAs:")
print(f"  Range: [{gini_values.min():.4f}, {gini_values.max():.4f}]")
print(f"  Mean: {gini_values.mean():.4f}")
print(f"  Std: {gini_values.std():.4f}")

r_gini_omega = np.corrcoef(gini_values, df.omega.values)[0, 1]
r_gini_entropy = np.corrcoef(gini_values, df.entropy_bits.values)[0, 1]
r_gini_cycle = np.corrcoef(gini_values, df.avg_cycle.values)[0, 1]
print(f"\nCorrelations:")
print(f"  r(Gini, omega) = {r_gini_omega:.4f}")
print(f"  r(Gini, entropy) = {r_gini_entropy:.4f}")
print(f"  r(Gini, avg_cycle) = {r_gini_cycle:.4f}")

named = {"A":(0,1,2,3,4),"B":(0,6,7,8,9),"G":(0,11,7,8,9),"MIN":(0,0,0,0,0),"MAX":(0,9,9,9,9)}
print(f"\n{'ISA':<6} {'Gini':>8} {'Omega':>8} {'Reachable':>10}")
for name, key in named.items():
    idx = np.where((ops[:,0]==key[1])&(ops[:,1]==key[2])&(ops[:,2]==key[3])&(ops[:,3]==key[4]))[0]
    if len(idx) > 0:
        i = idx[0]
        reach = int(np.sum(k_prog[i] >= 0))
        print(f"{name:<6} {gini_values[i]:>8.4f} {halting[i]/1679616:>8.4f} {reach:>10}")

print(f"\n\n=== PART 2: I(ISA; OUTPUT) ===", flush=True)

P = hist.astype(np.float64)
for i in range(n_isas):
    if halting[i] > 0:
        P[i] /= halting[i]

p_marginal = P.mean(axis=0)
p_marginal_nz = p_marginal[p_marginal > 0]
H_output = -np.sum(p_marginal_nz * np.log2(p_marginal_nz))

H_output_given_isa = 0
for i in range(n_isas):
    p_nz = P[i][P[i] > 0]
    if len(p_nz) > 0:
        H_output_given_isa += -np.sum(p_nz * np.log2(p_nz))
H_output_given_isa /= n_isas

MI = H_output - H_output_given_isa

print(f"H(output) = {H_output:.4f} bits")
print(f"H(output | ISA) = {H_output_given_isa:.4f} bits")
print(f"I(ISA; output) = {MI:.4f} bits")
print(f"I / H(output) = {MI/H_output*100:.1f}%")
print(f"Knowing the ISA determines {MI/H_output*100:.1f}% of the output uncertainty.")

print(f"\n\n=== PART 3: OUTPUT DISTRIBUTION CONVERGENCE ===", flush=True)

SPACE_N = {3: 216, 4: 1296, 5: 7776, 6: 46656, 7: 279936, 8: 1679616}

@numba.njit
def apply_op_nb(op_id, a, b):
    if op_id == 0: return (a+1)&0xFF, b
    elif op_id == 1: return (a-1)&0xFF, b
    elif op_id == 2: return b, a
    elif op_id == 3: return (a+b)&0xFF, b
    elif op_id == 4: return a^b, b
    elif op_id == 6: return (-a)&0xFF, b
    elif op_id == 7: return a, a
    elif op_id == 8: return (a-b)&0xFF, b
    elif op_id == 9: return a&b, b
    elif op_id == 10: return a|b, b
    elif op_id == 11: return a>>1, b
    elif op_id == 12: return (a<<1)&0xFF, b
    elif op_id == 13: return (~a)&0xFF, b
    else: return a, b

@numba.njit
def output_dist_at_length(ops_arr, prog_len):
    space = 1
    for _ in range(prog_len):
        space *= 6
    hist_out = np.zeros(256, dtype=np.int64)
    halts_out = 0
    for prog in range(space):
        tmp = prog
        p = np.empty(prog_len, dtype=np.int32)
        for i in range(prog_len):
            p[i] = tmp % 6; tmp //= 6
        a, b, pc = 0, 0, 0
        halted = False
        for step in range(256):
            if pc >= prog_len:
                halted = True; break
            opcode = p[pc]
            if opcode == 5:
                if a != 0: pc = 0
                else: pc += 1
            else:
                a, b = apply_op_nb(ops_arr[opcode], a, b)
                pc += 1
        if halted:
            halts_out += 1
            hist_out[a] += 1
    return halts_out, hist_out

print("JIT warmup...", flush=True)
ops_a = np.array([0,1,2,3,4], dtype=np.int32)
output_dist_at_length(ops_a, 3)
print("Ready.", flush=True)

test_isas = [("A",[0,1,2,3,4]), ("B",[0,6,7,8,9]), ("G",[0,11,7,8,9])]

for name, op_list in test_isas:
    print(f"\n{name}: output distribution convergence")
    print(f"{'N':>3} {'Programs':>10} {'Halting':>10} {'Omega':>8} {'Entropy':>8} {'Reach':>6} {'Top output':>12}")
    print("-" * 65)
    prev_dist = None
    for N in range(3, 9):
        ops_arr = np.array(op_list, dtype=np.int32)
        h, dist = output_dist_at_length(ops_arr, N)
        space = 6**N
        omega = h / space
        p = dist.astype(np.float64) / h if h > 0 else dist.astype(np.float64)
        p_nz = p[p > 0]
        entropy = -np.sum(p_nz * np.log2(p_nz)) if len(p_nz) > 0 else 0
        reach = int(np.sum(dist > 0))
        top_out = int(np.argmax(dist))
        top_frac = dist[top_out] / h if h > 0 else 0

        delta_str = ""
        if prev_dist is not None and h > 0:
            prev_p = prev_dist.astype(np.float64) / prev_dist.sum() if prev_dist.sum() > 0 else prev_dist.astype(np.float64)
            tv = 0.5 * np.sum(np.abs(p - prev_p))
            delta_str = f"  TV={tv:.4f}"

        print(f"{N:>3} {space:>10} {h:>10} {omega:>8.4f} {entropy:>8.3f} {reach:>6} {top_out:>4}({top_frac:.3f}){delta_str}")
        prev_dist = dist
