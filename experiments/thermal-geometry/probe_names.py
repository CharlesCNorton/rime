#!/usr/bin/env python3
"""Pre-place script: dump cell names and available BEL locations."""

ring_cells = []
for name, cell in ctx.cells:
    if "gen_ring" in name or "inv" in name:
        ring_cells.append((name, str(cell.type)))

print(f"Ring cells found: {len(ring_cells)}")
for name, ctype in ring_cells[:25]:
    print(f"  CELL: {name}  TYPE: {ctype}")

print("\nSample TRELLIS_COMB BELs:")
count = 0
for bel in ctx.getBels():
    bel_type = ctx.getBelType(bel)
    if "COMB" in str(bel_type) and count < 20:
        loc = ctx.getBelLocation(bel)
        print(f"  BEL: x={loc.x} y={loc.y} z={loc.z}")
        count += 1

xs = set()
ys = set()
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        xs.add(loc.x)
        ys.add(loc.y)
print(f"\nCOMB BEL range: x={min(xs)}-{max(xs)}, y={min(ys)}-{max(ys)}")
print(f"  {len(xs)} unique x, {len(ys)} unique y")
