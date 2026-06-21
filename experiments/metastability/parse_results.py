#!/usr/bin/env python3
"""Parse MTBF metastability experiment output and compute τ bound."""
import math
import sys
from pathlib import Path


def parse(path):
    text = Path(path).read_text(errors="replace")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    samples = None
    failures = {}
    freq_snaps = []

    for line in lines:
        if line.startswith("S,"):
            samples = int(line.split(",")[1], 16)
        elif line.startswith("C") and ",P" in line:
            parts = line.split(",")
            ch = int(parts[0][1:])
            pair = int(parts[1][1:])
            count = int(parts[2], 16)
            failures[(ch, pair)] = count
        elif line.startswith("F,"):
            parts = line.split(",")
            idx = int(parts[1], 16)
            edges = int(parts[2], 16)
            freq_snaps.append((idx, edges))

    if samples is None:
        print("No sample count found.")
        return

    chains = max(ch for ch, _ in failures) + 1 if failures else 0
    pairs = max(p for _, p in failures) + 1 if failures else 0
    total_failures = sum(failures.values())

    print(f"Samples:        {samples:,}")
    print(f"Chains:         {chains}")
    print(f"Pairs/chain:    {pairs}")
    print(f"Total failures: {total_failures}")
    print()

    for ch in range(chains):
        counts = [failures.get((ch, p), 0) for p in range(pairs)]
        print(f"  Chain {ch}: {counts}")

    if freq_snaps:
        interval_sec = 10.0
        freqs = [edges / interval_sec for _, edges in freq_snaps]
        sys_freq = 13333333.0

        print(f"\nRing oscillator ({len(freq_snaps)} snapshots, {interval_sec}s intervals):")
        print(f"  First:    {freqs[0]:>12,.0f} Hz  ({freqs[0]/1e6:.4f} MHz)")
        print(f"  Last:     {freqs[-1]:>12,.0f} Hz  ({freqs[-1]/1e6:.4f} MHz)")
        print(f"  Mean:     {sum(freqs)/len(freqs):>12,.0f} Hz  ({sum(freqs)/len(freqs)/1e6:.4f} MHz)")
        print(f"  Min:      {min(freqs):>12,.0f} Hz")
        print(f"  Max:      {max(freqs):>12,.0f} Hz")
        print(f"  Drift:    {freqs[0]-freqs[-1]:>+12,.0f} Hz over {len(freq_snaps)*interval_sec/60:.0f} min")
        print(f"  Sys clk:  {sys_freq:>12,.0f} Hz  ({sys_freq/1e6:.4f} MHz)")

        mean_beat = sum(freqs) / len(freqs)
        total_meta_measured = mean_beat * len(freq_snaps) * interval_sec
        print(f"\n  Measured beat freq (mean): {mean_beat:,.0f} Hz")
        print(f"  Total meta events (measured): {total_meta_measured:,.0f}")

    t_cq = 300e-12

    if total_failures == 0 and samples > 0:
        print("\n--- tau bound ---")
        print(f"t_clk_to_q estimate: {t_cq*1e12:.0f} ps")

        if freq_snaps:
            tau_meas = t_cq / math.log(total_meta_measured)
            print("\nMeasured beat frequency method:")
            print(f"  N_events:  {total_meta_measured:,.0f}")
            print(f"  ln(N):     {math.log(total_meta_measured):.2f}")
            print(f"  tau <        {tau_meas*1e12:.1f} ps")

        f_ring_est = 13e6
        t_sh = 300e-12
        accum_time = samples / 13.33e6
        meta_conservative = f_ring_est * accum_time * (t_sh * 13.33e6)
        meta_conservative = f_ring_est * accum_time * t_sh * 13.33e6
        meta_conservative = f_ring_est * accum_time * (t_sh / (1.0/13.33e6))
        tau_cons = t_cq / math.log(meta_conservative) if meta_conservative > 1 else float('inf')
        print("\nConservative setup/hold window method:")
        print(f"  N_events:  {meta_conservative:,.0f}")
        print(f"  ln(N):     {math.log(meta_conservative):.2f}")
        print(f"  tau <        {tau_cons*1e12:.1f} ps")

    elif total_failures > 0:
        print("\nFailures detected — exponential fit for τ extraction:")
        for p in range(pairs - 1):
            c0 = sum(failures.get((ch, p), 0) for ch in range(chains))
            c1 = sum(failures.get((ch, p + 1), 0) for ch in range(chains))
            if c0 > 0 and c1 > 0 and c1 < c0:
                tau = -t_cq / math.log(c1 / c0)
                print(f"  Pair {p}→{p+1}: ratio={c1/c0:.6f}, tau = {tau*1e12:.1f} ps")


if __name__ == "__main__":
    parse(sys.argv[1] if len(sys.argv) > 1 else "results_deep.txt")
