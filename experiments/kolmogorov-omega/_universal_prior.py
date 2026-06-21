#!/usr/bin/env python3
"""Empirical universal prior: P_univ(x) = mean P(x|ISA) over all 38,416 ISAs.

The first exact empirical analogue of Solomonoff's universal prior,
computed over a complete machine class. Tests predictive power by
holding out ISAs and measuring KL divergence from the prior."""
import numpy as np
import pandas as pd
import json

data = np.load("experiments/kolmogorov-omega/output_tensor.npz")
hist = data["hist"]
halting = data["halting"]
ops = data["ops"]

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")
n_isas = len(hist)

print("=== EMPIRICAL UNIVERSAL PRIOR ===")
print(f"ISAs: {n_isas}")

P = hist.astype(np.float64)
for i in range(n_isas):
    if halting[i] > 0:
        P[i] /= halting[i]

P_univ = P.mean(axis=0)
P_univ_nz = P_univ[P_univ > 0]
H_univ = -np.sum(P_univ_nz * np.log2(P_univ_nz))

print(f"\nUniversal prior P_univ(x):")
print(f"  Entropy: {H_univ:.4f} bits")
print(f"  Nonzero bins: {(P_univ > 0).sum()} / 256")
print(f"  Max: P_univ({np.argmax(P_univ)}) = {P_univ.max():.6f}")
print(f"  Top 10 outputs:")
top10 = np.argsort(P_univ)[::-1][:10]
for x in top10:
    print(f"    x={x:3d}: P = {P_univ[x]:.6f}")

print(f"\nPredictive power: KL(P(x|ISA) || P_univ) for each ISA")
kl_divs = np.zeros(n_isas)
for i in range(n_isas):
    p = P[i]
    kl = 0.0
    for x in range(256):
        if p[x] > 0 and P_univ[x] > 0:
            kl += p[x] * np.log2(p[x] / P_univ[x])
        elif p[x] > 0 and P_univ[x] == 0:
            kl += 10.0
    kl_divs[i] = kl

print(f"  KL divergence range: [{kl_divs.min():.4f}, {kl_divs.max():.4f}] bits")
print(f"  Mean KL: {kl_divs.mean():.4f} bits")
print(f"  Median KL: {np.median(kl_divs):.4f} bits")

print(f"\n  ISAs closest to universal prior:")
closest = np.argsort(kl_divs)[:5]
for idx in closest:
    o = ops[idx]
    print(f"    ({o[0]},{o[1]},{o[2]},{o[3]}): KL = {kl_divs[idx]:.4f} bits, omega = {halting[idx]/1679616:.4f}")

print(f"\n  ISAs farthest from universal prior:")
farthest = np.argsort(kl_divs)[::-1][:5]
for idx in farthest:
    o = ops[idx]
    print(f"    ({o[0]},{o[1]},{o[2]},{o[3]}): KL = {kl_divs[idx]:.4f} bits, omega = {halting[idx]/1679616:.4f}")

print(f"\nLeave-one-out predictive test:")
errors = []
for trial in range(100):
    rng = np.random.RandomState(trial)
    held_out = rng.randint(n_isas)
    mask = np.ones(n_isas, dtype=bool)
    mask[held_out] = False
    P_loo = P[mask].mean(axis=0)
    p_held = P[held_out]
    kl = 0.0
    for x in range(256):
        if p_held[x] > 0 and P_loo[x] > 0:
            kl += p_held[x] * np.log2(p_held[x] / P_loo[x])
        elif p_held[x] > 0:
            kl += 10.0
    errors.append(kl)
errors = np.array(errors)
print(f"  100 random holdouts: KL mean = {errors.mean():.4f}, std = {errors.std():.4f}")

np.savez_compressed("experiments/kolmogorov-omega/universal_prior.npz",
                     P_univ=P_univ, kl_divs=kl_divs)
results = {
    "entropy_bits": round(float(H_univ), 4),
    "nonzero_bins": int((P_univ > 0).sum()),
    "kl_mean": round(float(kl_divs.mean()), 4),
    "kl_median": round(float(np.median(kl_divs)), 4),
    "top_outputs": [(int(x), round(float(P_univ[x]), 6)) for x in top10],
    "loo_kl_mean": round(float(errors.mean()), 4),
}
with open("experiments/kolmogorov-omega/universal_prior.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nWrote universal_prior.npz and universal_prior.json")
