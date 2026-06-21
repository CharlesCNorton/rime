#!/usr/bin/env python3
"""Compute differential frequency maps from RF stimulus experiment data.

Compares baseline sweeps against stimulus sweeps to reveal spatial
patterns of RF coupling on the die.
"""

import sys
from pathlib import Path


def parse_phased_log(path: str):
    """Parse a stimulus experiment log with phase markers."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()

    config = {}
    phases = {"BASELINE": {}, "STIMULUS": {}, "POST-STIMULUS": {}}
    current_phase = "BASELINE"

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            if "PHASE: STIMULUS" in line:
                current_phase = "STIMULUS"
            elif "PHASE: POST-STIMULUS" in line:
                current_phase = "POST-STIMULUS"
            elif "PHASE: BASELINE" in line:
                current_phase = "BASELINE"
            continue

        if line.startswith("G,"):
            parts = line[2:].split(",")
            if len(parts) >= 4:
                config = {
                    "grid_w": int(parts[0], 16),
                    "grid_h": int(parts[1], 16),
                    "meas_ms": int(parts[2], 16),
                    "total_rings": int(parts[3], 16),
                }

        elif line.startswith("R,"):
            parts = line[2:].split(",")
            if len(parts) >= 3:
                sweep = int(parts[0], 16)
                idx = int(parts[1], 16)
                count = int(parts[2], 16)
                if sweep not in phases[current_phase]:
                    phases[current_phase][sweep] = {}
                phases[current_phase][sweep][idx] = count

    return config, phases


def compute_mean_map(sweeps):
    """Average frequency map across multiple sweeps."""
    if not sweeps:
        return {}
    all_indices = set()
    for s in sweeps.values():
        all_indices.update(s.keys())
    mean_map = {}
    for idx in sorted(all_indices):
        values = [s[idx] for s in sweeps.values() if idx in s]
        mean_map[idx] = sum(values) / len(values) if values else 0
    return mean_map


def print_map(title, freq_map, grid_w, grid_h, fmt="{:6.0f}"):
    """Print a frequency map as a grid."""
    print(f"\n{title}")
    for row in range(grid_h):
        vals = []
        for col in range(grid_w):
            idx = row * grid_w + col
            vals.append(fmt.format(freq_map.get(idx, 0)))
        print(f"  Row {row:2d}: {' '.join(vals)}")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <results_file>")
        sys.exit(1)

    config, phases = parse_phased_log(sys.argv[1])

    print("=" * 70)
    print("RF STIMULUS DIFFERENTIAL ANALYSIS")
    print("=" * 70)

    if config:
        print(f"Grid: {config['grid_w']}x{config['grid_h']} = "
              f"{config['total_rings']} rings")

    for phase_name, sweeps in phases.items():
        print(f"\n{phase_name}: {len(sweeps)} sweeps captured")

    grid_w = config.get("grid_w", 16)
    grid_h = config.get("grid_h", 16)

    baseline_map = compute_mean_map(phases["BASELINE"])
    stimulus_map = compute_mean_map(phases["STIMULUS"])
    post_map = compute_mean_map(phases["POST-STIMULUS"])

    if not baseline_map:
        print("No baseline data. Cannot compute differential.")
        return

    if baseline_map:
        print_map("BASELINE (mean edge counts per 1ms)", baseline_map, grid_w, grid_h)

    if stimulus_map and baseline_map:
        diff_map = {}
        pct_map = {}
        for idx in baseline_map:
            if idx in stimulus_map:
                diff_map[idx] = stimulus_map[idx] - baseline_map[idx]
                if baseline_map[idx] > 0:
                    pct_map[idx] = diff_map[idx] / baseline_map[idx] * 100
                else:
                    pct_map[idx] = 0

        print_map("DIFFERENTIAL (stimulus - baseline, edge counts)",
                  diff_map, grid_w, grid_h, fmt="{:+6.0f}")
        print_map("DIFFERENTIAL (% shift from baseline)",
                  pct_map, grid_w, grid_h, fmt="{:+5.2f}%")

        diffs = list(diff_map.values())
        if diffs:
            mean_diff = sum(diffs) / len(diffs)
            max_diff = max(diffs, key=abs)
            max_idx = [k for k, v in diff_map.items() if v == max_diff][0]
            max_row, max_col = divmod(max_idx, grid_w)

            pcts = list(pct_map.values())
            mean_pct = sum(pcts) / len(pcts)
            max_pct = max(pcts, key=abs)

            print("\nDifferential summary:")
            print(f"  Mean shift: {mean_diff:+.1f} counts ({mean_pct:+.3f}%)")
            print(f"  Max shift: {max_diff:+.0f} counts at ring {max_idx} "
                  f"(row={max_row}, col={max_col})")
            print(f"  Max % shift: {max_pct:+.3f}%")

            block_names = ["Block 1 (rows 0-3)", "Block 2 (rows 4-7)",
                          "Block 3 (rows 8-11)", "Block 4 (rows 12-15)"]
            for b in range(4):
                block_diffs = [diff_map.get(r * grid_w + c, 0)
                              for r in range(b * 4, (b + 1) * 4)
                              for c in range(grid_w)]
                if block_diffs:
                    block_mean = sum(block_diffs) / len(block_diffs)
                    print(f"  {block_names[b]}: mean shift {block_mean:+.1f}")

    if post_map and baseline_map:
        recovery_map = {}
        for idx in baseline_map:
            if idx in post_map:
                recovery_map[idx] = post_map[idx] - baseline_map[idx]
        recovery_vals = list(recovery_map.values())
        if recovery_vals:
            mean_recovery = sum(recovery_vals) / len(recovery_vals)
            print("\nPost-stimulus recovery:")
            print(f"  Mean residual shift: {mean_recovery:+.1f} counts")
            if abs(mean_recovery) < abs(mean_diff) * 0.1:
                print("  Recovery complete (residual < 10% of stimulus effect)")
            else:
                print("  Partial recovery (thermal or persistent effect)")


if __name__ == "__main__":
    main()
