#!/usr/bin/env python3
"""Complexity phase diagram: omega vs cycle length vs output entropy.
3D point cloud colored by coupling type. Cluster analysis."""
import pandas as pd
import numpy as np
from collections import Counter

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")

print("=== COMPLEXITY PHASE DIAGRAM ===")
print(f"ISAs: {len(df)}")
print()

print("Per-coupling-type centroids:")
print(f"{'Coupling':<15} {'N':>6} {'Omega':>8} {'AvgCyc':>8} {'Entropy':>8}")
print("-" * 50)
for coupling in ["bidirectional", "one-way", "none"]:
    sub = df[df.coupling == coupling]
    print(f"{coupling:<15} {len(sub):>6} {sub.omega.mean():>8.4f} {sub.avg_cycle.mean():>8.1f} {sub.entropy_bits.mean():>8.2f}")

print()
print("Cross-observable correlations:")
from itertools import combinations
obs = {"omega": df.omega, "avg_cycle": df.avg_cycle, "entropy": df.entropy_bits}
for (n1, v1), (n2, v2) in combinations(obs.items(), 2):
    r = np.corrcoef(v1, v2)[0, 1]
    print(f"  r({n1}, {n2}) = {r:.4f}")

print()
print("K-means clustering (k=3,4,5,6):")
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

X = StandardScaler().fit_transform(df[["omega", "avg_cycle", "entropy_bits"]].values)
for k in [3, 4, 5, 6]:
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(X)
    inertia = km.inertia_
    sizes = Counter(labels)
    size_str = " ".join(f"{sizes[i]}" for i in range(k))
    print(f"  k={k}: inertia={inertia:.0f}  sizes=[{size_str}]")

print()
km4 = KMeans(n_clusters=4, n_init=10, random_state=42)
labels = km4.fit_predict(X)
df["cluster"] = labels
print("4-cluster breakdown:")
print(f"{'Cluster':<8} {'N':>6} {'Omega':>8} {'AvgCyc':>8} {'Entropy':>8} {'Coupling mode':>15}")
print("-" * 60)
for c in range(4):
    sub = df[df.cluster == c]
    mode_coupling = sub.coupling.mode().iloc[0] if len(sub) > 0 else ""
    print(f"{c:<8} {len(sub):>6} {sub.omega.mean():>8.4f} {sub.avg_cycle.mean():>8.1f} {sub.entropy_bits.mean():>8.2f} {mode_coupling:>15}")

print()
print("Extremes in 3D space:")
print("  Highest entropy:", df.loc[df.entropy_bits.idxmax(), ["op1","op2","op3","op4","omega","avg_cycle","entropy_bits"]].to_dict())
print("  Lowest entropy:", df.loc[df.entropy_bits.idxmin(), ["op1","op2","op3","op4","omega","avg_cycle","entropy_bits"]].to_dict())
print("  Longest cycles:", df.loc[df.avg_cycle.idxmax(), ["op1","op2","op3","op4","omega","avg_cycle","entropy_bits"]].to_dict())
print("  Shortest cycles:", df.loc[df.avg_cycle.idxmin(), ["op1","op2","op3","op4","omega","avg_cycle","entropy_bits"]].to_dict())
