#!/usr/bin/env python3
"""Generate LPF LOCATE constraints for Ember's ring placement."""

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


with open("ember_ring_map.txt", "w") as f:
    f.write("# Ember ring placement map\n")
    f.write("# ring_idx, col(x), row(y), path\n")
    for i, (x, y) in enumerate(all_tiles):
        path = "A" if i < 64 else ("B" if i < 128 else "C")
        f.write(f"{i},{x},{y},{path}\n")

print(f"Generated ember_ring_map.txt with {len(all_tiles)} positions")
print(f"Path A: rows {sorted(set(r for c,r in path_a))}")
print(f"Path B: rows {sorted(set(r for c,r in path_b))}")
print(f"Path C: rows {sorted(set(r for c,r in path_c))}")
