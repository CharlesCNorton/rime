#!/usr/bin/env python3
"""ANOVA decomposition of output entropy — same method as omega irreducibility.
Is entropy also irreducible, or does it have different interaction structure?"""
import pandas as pd
import numpy as np

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")

print("=== ENTROPY ANOVA DECOMPOSITION ===")
print(f"ISAs: {len(df)}")
print()

total_var_omega = df.omega.var()
total_var_entropy = df.entropy_bits.var()
total_var_cycle = df.avg_cycle.var()

print(f"Total variance: omega={total_var_omega:.6f}, entropy={total_var_entropy:.4f}, cycle={total_var_cycle:.1f}")
print()

slots = ["op1", "op2", "op3", "op4"]

def r_squared(target, conditioning_cols):
    groups = df.groupby(conditioning_cols)[target]
    within_var = groups.var().mean()
    total = df[target].var()
    return 1 - within_var / total if total > 0 else 0

print(f"{'Conditioning':<25} {'R2(omega)':>10} {'R2(entropy)':>12} {'R2(cycle)':>10}")
print("-" * 60)

for k in [1, 2, 3, 4]:
    from itertools import combinations
    combos = list(combinations(range(4), k))
    r2_omega_vals = []
    r2_entropy_vals = []
    r2_cycle_vals = []
    for combo in combos:
        cols = [slots[i] for i in combo]
        r2_omega_vals.append(r_squared("omega", cols))
        r2_entropy_vals.append(r_squared("entropy_bits", cols))
        r2_cycle_vals.append(r_squared("avg_cycle", cols))
    r2_o = np.mean(r2_omega_vals)
    r2_e = np.mean(r2_entropy_vals)
    r2_c = np.mean(r2_cycle_vals)
    label = f"{k} opcode{'s' if k > 1 else ''} (mean of C(4,{k})={len(combos)})"
    print(f"{label:<25} {r2_o:>10.4f} {r2_e:>12.4f} {r2_c:>10.4f}")

print()
print("Interaction decomposition:")
print(f"{'Source':<20} {'Omega':>8} {'Entropy':>10} {'Cycle':>8}")
print("-" * 50)

r2 = {}
for obs in ["omega", "entropy_bits", "avg_cycle"]:
    r2[obs] = {}
    for k in [1, 2, 3, 4]:
        combos = list(combinations(range(4), k))
        vals = [r_squared(obs, [slots[i] for i in combo]) for combo in combos]
        r2[obs][k] = np.mean(vals)

for obs_name, obs_col in [("Omega", "omega"), ("Entropy", "entropy_bits"), ("Cycle", "avg_cycle")]:
    pass

labels = ["Main effects", "2-way interact", "3-way interact", "4-way interact"]
for i, label in enumerate(labels):
    k = i + 1
    o_val = r2["omega"][k] - (r2["omega"][k-1] if k > 1 else 0)
    e_val = r2["entropy_bits"][k] - (r2["entropy_bits"][k-1] if k > 1 else 0)
    c_val = r2["avg_cycle"][k] - (r2["avg_cycle"][k-1] if k > 1 else 0)
    print(f"{label:<20} {o_val:>8.4f} {e_val:>10.4f} {c_val:>8.4f}")

print()
print("Key question: does entropy have the same monotonically increasing")
print("interaction structure as omega, or is it more/less reducible?")
