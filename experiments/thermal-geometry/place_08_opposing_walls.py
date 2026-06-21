# Opposing walls: two dense bands at opposite die edges with empty center.
# nextpnr placement constraint script (runs inside nextpnr Python context).
# Part of the thermal-geometry experiment — see README.md.

bel_lookup = {}
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        bel_lookup[(loc.x, loc.y, loc.z)] = bel

tiles = [(5, 14), (65, 14), (5, 15), (65, 15), (5, 16), (65, 16), (5, 17), (65, 17), (5, 18), (65, 18), (5, 19), (65, 19), (5, 20), (65, 20), (5, 21), (65, 21), (5, 22), (65, 22), (5, 23), (65, 23), (5, 24), (65, 24), (20, 17), (20, 19), (20, 21), (36, 17), (36, 19), (36, 21), (50, 17), (50, 19), (50, 21)]

placed = 0
for name, cell in ctx.cells:
    if "gen_ring[" not in name or "gen_st[" not in name:
        continue
    ring_idx = int(name.split("gen_ring[")[1].split("]")[0])
    stage = int(name.split("gen_st[")[1].split("]")[0])
    if ring_idx < len(tiles):
        tx, ty = tiles[ring_idx]
        key = (tx, ty, stage * 4)
        if key in bel_lookup:
            ctx.bindBel(bel_lookup[key], cell, PlaceStrength.STRENGTH_LOCKED)
            placed += 1

print(f"{placed} / 155 constrained for 08_opposing_walls (extras float)")
