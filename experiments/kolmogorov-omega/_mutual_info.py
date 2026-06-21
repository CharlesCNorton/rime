#!/usr/bin/env python3
import pandas as pd
import numpy as np
from itertools import combinations
from sklearn.metrics import mutual_info_score

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")
omega_binned = pd.qcut(df.omega, q=50, labels=False, duplicates="drop")

features = {
    "op1": df.op1, "op2": df.op2, "op3": df.op3, "op4": df.op4,
    "has_swp": df.has_swp.astype(int), "has_mov": df.has_mov.astype(int),
    "has_and": df.has_and.astype(int), "has_shr": df.has_shr.astype(int),
    "involution_count": df.involution_count,
    "coupling": pd.Categorical(df.coupling).codes,
}

H_omega = mutual_info_score(omega_binned, omega_binned)
print(f"H(Omega) = {H_omega:.4f} nats")
print()

print(f"{'Feature':>20s}  {'MI':>8s}  {'MI/H':>8s}")
print("-" * 42)
single_mis = {}
for name, feat in features.items():
    mi = mutual_info_score(omega_binned, feat)
    single_mis[name] = mi
    print(f"{name:>20s}  {mi:8.4f}  {mi/H_omega:8.4f}")

print()
print("Top 10 2D projections:")
pair_mis = []
feat_names = list(features.keys())
for i, j in combinations(range(len(feat_names)), 2):
    n1, n2 = feat_names[i], feat_names[j]
    combined = features[n1].astype(str) + "_" + features[n2].astype(str)
    mi = mutual_info_score(omega_binned, combined)
    pair_mis.append((mi, n1, n2))
pair_mis.sort(reverse=True)
for mi, n1, n2 in pair_mis[:10]:
    print(f"  {n1+'+'+n2:>30s}  {mi:8.4f}  {mi/H_omega:8.4f}")

print()
combined_4d = df.op1.astype(str)+"_"+df.op2.astype(str)+"_"+df.op3.astype(str)+"_"+df.op4.astype(str)
mi_4d = mutual_info_score(omega_binned, combined_4d)
print(f"4D (full ISA): MI = {mi_4d:.4f}  MI/H = {mi_4d/H_omega:.4f}")
print()

max_1d = max(single_mis.values())
max_2d = pair_mis[0][0]
print(f"1D best: {max_1d/H_omega*100:.1f}%")
print(f"2D best: {max_2d/H_omega*100:.1f}%")
print(f"4D full: {mi_4d/H_omega*100:.1f}%")
print(f"Gap 1D->4D: {(mi_4d-max_1d)/H_omega*100:.1f} pp")
