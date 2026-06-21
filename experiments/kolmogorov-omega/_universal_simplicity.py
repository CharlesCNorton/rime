#!/usr/bin/env python3
"""Universal vs ISA-specific complexity.
Are the 9 universally reachable outputs also universally probable?"""
import numpy as np
import pandas as pd

data = np.load("experiments/kolmogorov-omega/output_tensor.npz")
hist = data["hist"]
halting = data["halting"]
ops = data["ops"]

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")

print("=== UNIVERSAL SIMPLICITY ===")
print(f"ISAs: {len(hist)}")
print()

P = hist.astype(np.float64)
for i in range(len(P)):
    if halting[i] > 0:
        P[i] /= halting[i]

reachable = (hist > 0)
reach_count = reachable.sum(axis=0)

universally_reachable = [x for x in range(256) if reach_count[x] == len(hist)]
print(f"Universally reachable outputs (produced by all {len(hist)} ISAs): {universally_reachable}")
print()

print("For each universally reachable output:")
print(f"{'Output':>7} {'Mean P':>10} {'Median P':>10} {'Min P':>10} {'Max P':>10} {'Mean rank':>10} {'CV':>8}")
print("-" * 70)

ranks_per_output = {}
for x in universally_reachable:
    p_x = P[:, x]
    for i in range(len(P)):
        row_p = P[i]
        nz = row_p[row_p > 0]
    all_ranks = []
    for i in range(len(P)):
        row_p = P[i]
        rank = (row_p > p_x[i]).sum() + 1
        all_ranks.append(rank)
    all_ranks = np.array(all_ranks)
    ranks_per_output[x] = all_ranks
    cv = p_x.std() / p_x.mean() if p_x.mean() > 0 else 0
    print(f"{x:>7d} {p_x.mean():>10.6f} {np.median(p_x):>10.6f} {p_x.min():>10.6f} {p_x.max():>10.6f} {all_ranks.mean():>10.1f} {cv:>8.2f}")

print()
print("Rank stability of universally reachable outputs:")
print("(Low mean rank = consistently probable across ISAs)")
print("(High CV of rank = rank varies wildly across ISAs)")
print()

print("Are universally reachable outputs also the MOST probable?")
top1_counts = np.zeros(256, dtype=int)
top5_counts = np.zeros(256, dtype=int)
for i in range(len(P)):
    row = P[i]
    sorted_idx = np.argsort(row)[::-1]
    if row[sorted_idx[0]] > 0:
        top1_counts[sorted_idx[0]] += 1
    for j in range(min(5, len(sorted_idx))):
        if row[sorted_idx[j]] > 0:
            top5_counts[sorted_idx[j]] += 1

print(f"\n{'Output':>7} {'#1 most probable':>18} {'Top-5':>8} {'Universal':>10}")
print("-" * 50)
top_outputs = np.argsort(top1_counts)[::-1][:20]
for x in top_outputs:
    univ = "yes" if x in universally_reachable else ""
    print(f"{x:>7d} {top1_counts[x]:>18d} {top5_counts[x]:>8d} {univ:>10}")

print()
never_top1 = [x for x in universally_reachable if top1_counts[x] == 0]
always_top5 = [x for x in universally_reachable if top5_counts[x] == len(hist)]
print(f"Universally reachable but NEVER most probable: {never_top1}")
print(f"Universally reachable AND always top-5: {always_top5}")

print()
print("Complexity ranking stability across ISAs:")
print("For each pair of universally reachable outputs (x, y):")
print("  fraction of ISAs where P(x) > P(y)")
if len(universally_reachable) >= 2:
    from itertools import combinations
    swaps = []
    for x, y in combinations(universally_reachable, 2):
        frac_x_gt_y = (P[:, x] > P[:, y]).mean()
        if 0.1 < frac_x_gt_y < 0.9:
            swaps.append((x, y, frac_x_gt_y))
    swaps.sort(key=lambda t: abs(t[2] - 0.5))
    print(f"  Pairs where ranking swaps (10-90% split): {len(swaps)}")
    for x, y, f in swaps[:10]:
        print(f"    x={x}, y={y}: P(x)>P(y) in {f*100:.1f}% of ISAs")
