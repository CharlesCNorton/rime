# Single hot row: all rings concentrated in one row for maximum local heating.
# nextpnr placement constraint script (runs inside nextpnr Python context).
# Part of the thermal-geometry experiment — see README.md.

bel_lookup = {}
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        bel_lookup[(loc.x, loc.y, loc.z)] = bel

tiles = [(2, 19), (3, 19), (4, 19), (5, 19), (6, 19), (7, 19), (8, 19), (9, 19), (10, 19), (11, 19), (12, 19), (13, 19), (14, 19), (15, 19), (16, 19), (17, 19), (18, 19), (19, 19), (20, 19), (21, 19), (22, 19), (23, 19), (24, 19), (25, 19), (26, 19), (27, 19), (28, 19), (29, 19), (30, 19), (31, 19), (32, 19), (33, 19), (34, 19), (35, 19), (36, 19), (37, 19), (38, 19), (39, 19), (40, 19), (41, 19), (42, 19), (43, 19), (44, 19), (45, 19), (46, 19), (47, 19), (48, 19), (49, 19), (50, 19), (51, 19), (52, 19), (53, 19), (54, 19), (55, 19), (56, 19), (57, 19), (58, 19), (59, 19), (60, 19), (61, 19), (62, 19), (63, 19), (64, 19), (65, 19), (66, 19), (67, 19), (68, 19), (69, 19), (70, 19), (36, 18), (36, 20), (36, 17), (36, 21), (36, 15), (36, 23)]

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

print(f"{placed} / 375 constrained for 05_single_hot_row (extras float)")
