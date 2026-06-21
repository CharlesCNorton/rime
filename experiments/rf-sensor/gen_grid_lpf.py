#!/usr/bin/env python3
"""Generate LPF LOCATE constraints for a 16x16 ring oscillator grid.

Places 256 rings across all 4 logic blocks of the ECP5-25F die.
Each ring has 5 LUT4 stages needing 3 slices (A, B, C).

Die layout (44 rows x 69 columns):
  Block 1: rows  2-12  (below DSP stripe at row 13)
  Block 2: rows 14-24  (below BRAM stripe at row 25)
  Block 3: rows 26-36  (below BRAM stripe at row 37)
  Block 4: rows 38-44  (top of die)
"""

ROWS = [
    3, 6, 9, 12,
    15, 18, 21, 24,
    27, 30, 33, 36,
    38, 40, 42, 44,
]

COLS = [2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50, 54, 58, 62]

RING_STAGES = 5


def generate_constraints():
    lines = []
    lines.append("# RF sensor grid placement constraints")
    lines.append(f"# {len(ROWS)}x{len(COLS)} = {len(ROWS)*len(COLS)} rings, "
                 f"{len(ROWS)*len(COLS)*RING_STAGES} constraints")
    lines.append(f"# Rows: {ROWS}")
    lines.append(f"# Cols: {COLS}")
    lines.append("")

    ring_idx = 0
    for row_idx, row in enumerate(ROWS):
        for col_idx, col in enumerate(COLS):
            for stage in range(RING_STAGES):
                cell_name = f"gen_ring[{ring_idx}].gen_st[{stage}].inv"
                slice_letter = chr(ord('A') + stage // 2)
                lines.append(
                    f'LOCATE COMP "{cell_name}" '
                    f'SITE "R{row}C{col}{slice_letter}";'
                )
            ring_idx += 1

    return lines


def main():
    lines = generate_constraints()

    with open("rf_sensor_placement.lpf", "w") as f:
        for line in lines:
            f.write(line + "\n")

    print(f"Generated rf_sensor_placement.lpf: "
          f"{len([ln for ln in lines if ln.startswith('LOCATE')])} constraints "
          f"for {len(ROWS)*len(COLS)} rings")

    import os
    base_lpf = os.path.join(
        os.path.dirname(__file__), "..", "..", "firmware", "core", "v1.3",
        "icepi-zero-v1_3.lpf"
    )
    if os.path.exists(base_lpf):
        with open(base_lpf) as f:
            base_text = f.read()
        base_text = base_text.replace(
            "MASTER_SPI_PORT=ENABLE", "MASTER_SPI_PORT=DISABLE"
        )
        with open("icepi-zero.lpf", "w") as f:
            f.write(base_text)
            f.write("\n\n")
            for line in lines:
                f.write(line + "\n")
        print("Generated icepi-zero.lpf (merged base + placement)")
    else:
        print(f"Warning: base LPF not found at {base_lpf}")
        print("Generate icepi-zero.lpf manually by merging with the base LPF.")


if __name__ == "__main__":
    main()
