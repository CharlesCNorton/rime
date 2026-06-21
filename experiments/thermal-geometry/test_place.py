#!/usr/bin/env python3
"""Pre-place script: constrain 4 rings to specific tiles."""

print("PlaceStrength members:", dir(PlaceStrength))

placements = {
    0: (10, 5),
    1: (20, 5),
    2: (30, 5),
    3: (40, 5),
}

bel_lookup = {}
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        bel_lookup[(loc.x, loc.y, loc.z)] = bel

placed = 0
for name, cell in ctx.cells:
    for ring_idx, (tx, ty) in placements.items():
        prefix = f"gen_ring[{ring_idx}].gen_st["
        if prefix in name:
            stage = int(name.split("gen_st[")[1].split("]")[0])
            bel_z = stage * 4
            key = (tx, ty, bel_z)
            if key in bel_lookup:
                ctx.bindBel(bel_lookup[key], cell, PlaceStrength.STRENGTH_LOCKED)
                placed += 1

print(f"Total placed: {placed} / 20")
