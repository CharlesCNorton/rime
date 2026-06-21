#!/usr/bin/env python3
"""Generate LPF LOCATE constraints for Ember ring placement."""

def make_path(row_start, row_end, n_rings=64):
    rows = list(range(row_start, row_end + 1))
    cols = list(range(2, 71))
    n_rows = 4
    n_cols = 16
    row_step = max(1, len(rows) // n_rows)
    col_step = max(1, len(cols) // n_cols)
    tiles = []
    for ri in range(n_rows):
        r = rows[min(ri * row_step, len(rows) - 1)]
        for ci in range(n_cols):
            c = cols[min(ci * col_step, len(cols) - 1)]
            tiles.append((c, r))
            if len(tiles) >= n_rings:
                break
        if len(tiles) >= n_rings:
            break
    return tiles

path_a = make_path(2, 12)
path_b = make_path(14, 24)
path_c = make_path(26, 36)
all_tiles = path_a + path_b + path_c


lines = []
for ring_idx, (col, row) in enumerate(all_tiles):
    for stage in range(5):
        cell_name = f"gen_ring[{ring_idx}].gen_st[{stage}].inv"
        slice_letter = chr(ord('A') + stage // 2)
        lines.append(f'LOCATE COMP "{cell_name}" SITE "R{row}C{col}{slice_letter}";')

with open("ember_placement.lpf", "w") as f:
    f.write("# Ember ring placement constraints\n")
    f.write(f"# {len(all_tiles)} rings, {len(lines)} constraints\n\n")
    for line in lines:
        f.write(line + "\n")

print(f"Generated ember_placement.lpf: {len(lines)} constraints for {len(all_tiles)} rings")
