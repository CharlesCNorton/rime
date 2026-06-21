#!/usr/bin/env python3
"""Algorithmic mutual information between outputs.
Compute 256x256 output-output correlation matrix across ISA space."""
import numpy as np
import json
import os

data = np.load("experiments/kolmogorov-omega/output_tensor.npz")
hist = data["hist"]
halting = data["halting"]

print("=== OUTPUT MUTUAL INFORMATION ===")
print(f"ISAs: {len(hist)}, outputs: 256")

P = hist.astype(np.float64)
for i in range(len(P)):
    if halting[i] > 0:
        P[i] /= halting[i]

reachable = (hist > 0).astype(np.int32)
reach_count = reachable.sum(axis=0)
print(f"Outputs reachable by all ISAs: {(reach_count == len(hist)).sum()}")
print(f"Outputs reachable by >50% ISAs: {(reach_count > len(hist)//2).sum()}")
print(f"Outputs reachable by <10% ISAs: {(reach_count < len(hist)//10).sum()}")

print("\nComputing 256x256 correlation matrix...")
corr = np.corrcoef(P.T)
corr = np.nan_to_num(corr, nan=0.0)

print(f"Correlation matrix shape: {corr.shape}")
print(f"Mean |r|: {np.abs(corr[np.triu_indices(256, k=1)]).mean():.4f}")
print(f"Max |r|: {np.abs(corr[np.triu_indices(256, k=1)]).max():.4f}")
print(f"Fraction |r| > 0.5: {(np.abs(corr[np.triu_indices(256, k=1)]) > 0.5).mean():.4f}")
print(f"Fraction |r| > 0.8: {(np.abs(corr[np.triu_indices(256, k=1)]) > 0.8).mean():.4f}")

np.savez_compressed("experiments/kolmogorov-omega/output_corr_matrix.npz", corr=corr, reach_count=reach_count)
print("Wrote output_corr_matrix.npz")

print("\nSpectral analysis of correlation matrix...")
eigenvalues = np.linalg.eigvalsh(corr)
eigenvalues = np.sort(eigenvalues)[::-1]
total_var = eigenvalues.sum()
cumvar = np.cumsum(eigenvalues) / total_var
print(f"Top eigenvalue: {eigenvalues[0]:.2f} ({eigenvalues[0]/total_var*100:.1f}%)")
print(f"Top 5: {eigenvalues[:5].sum()/total_var*100:.1f}%")
print(f"Top 10: {eigenvalues[:10].sum()/total_var*100:.1f}%")
print(f"Top 20: {eigenvalues[:20].sum()/total_var*100:.1f}%")
for pct in [0.5, 0.8, 0.9, 0.95, 0.99]:
    n = int(np.searchsorted(cumvar, pct)) + 1
    print(f"  {pct*100:.0f}% variance in {n} components")

print("\nHighly correlated output pairs (|r| > 0.9):")
pairs = []
for i in range(256):
    for j in range(i+1, 256):
        if abs(corr[i, j]) > 0.9:
            pairs.append((i, j, corr[i, j]))
pairs.sort(key=lambda x: -abs(x[2]))
for x, y, r in pairs[:20]:
    print(f"  output {x:3d} ~ output {y:3d}: r = {r:+.4f}")
if len(pairs) > 20:
    print(f"  ... {len(pairs) - 20} more pairs")
print(f"Total pairs with |r| > 0.9: {len(pairs)}")

universally_reachable = [x for x in range(256) if reach_count[x] == len(hist)]
print(f"\nUniversally reachable outputs: {universally_reachable}")
print("Mean P(x) for universally reachable:")
for x in universally_reachable:
    mean_p = P[:, x].mean()
    median_p = np.median(P[:, x])
    print(f"  x={x:3d}: mean P = {mean_p:.6f}, median P = {median_p:.6f}")
