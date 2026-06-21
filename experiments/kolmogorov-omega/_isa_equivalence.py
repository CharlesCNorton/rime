#!/usr/bin/env python3
"""ISA equivalence classes: groups of ISAs with identical output distributions.

Two ISAs are output-equivalent if P(x|ISA_1) = P(x|ISA_2) for all x.
These are gauge symmetries — internal opcode changes that leave the
observable unchanged. How many classes exist? How large? What algebraic
structure do they share?"""
import numpy as np
import pandas as pd
import json
from collections import defaultdict

data = np.load("experiments/kolmogorov-omega/output_tensor.npz")
hist = data["hist"]
halting = data["halting"]
ops_arr = data["ops"]

df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")
n_isas = len(hist)

OP_NAMES = {0:'INC',1:'DEC',2:'SWP',3:'ADD',4:'XOR',6:'NEG',7:'MOV',
            8:'SUB',9:'AND',10:'OR',11:'SHR',12:'SHL',13:'CPL',14:'NOP'}

def isa_label(i):
    o = ops_arr[i]
    names = [OP_NAMES.get(int(o[j]), '?') for j in range(4)]
    return f"INC {names[0]} {names[1]} {names[2]} {names[3]} JNZ"

print("=== ISA EQUIVALENCE CLASSES ===")
print(f"ISAs: {n_isas}\n")

print("Computing output distribution fingerprints...")
fingerprints = {}
for i in range(n_isas):
    fp = tuple(hist[i].tolist())
    if fp not in fingerprints:
        fingerprints[fp] = []
    fingerprints[fp].append(i)

classes = sorted(fingerprints.values(), key=lambda c: -len(c))
n_classes = len(classes)
sizes = [len(c) for c in classes]

print(f"Distinct output distributions: {n_classes}")
print(f"Equivalence classes with >1 member: {sum(1 for s in sizes if s > 1)}")
print(f"Largest class: {sizes[0]} ISAs")
print(f"Singleton classes: {sum(1 for s in sizes if s == 1)}")
print(f"Mean class size: {n_isas / n_classes:.1f}")
print()

print("Size distribution:")
size_counts = defaultdict(int)
for s in sizes:
    size_counts[s] += 1
for sz in sorted(size_counts.keys(), reverse=True)[:15]:
    print(f"  size {sz:>4d}: {size_counts[sz]:>5d} classes")
if len(size_counts) > 15:
    print(f"  ... {len(size_counts) - 15} more size levels")

print(f"\nLargest equivalence classes:")
print(f"{'Size':>5} {'Omega':>8} {'Entropy':>8} {'Reach':>6}  Members")
print("-" * 80)
for cls in classes[:10]:
    i0 = cls[0]
    omega = halting[i0] / 1679616
    p = hist[i0].astype(np.float64) / halting[i0] if halting[i0] > 0 else hist[i0].astype(np.float64)
    p_nz = p[p > 0]
    entropy = -np.sum(p_nz * np.log2(p_nz)) if len(p_nz) > 0 else 0
    reach = int(np.sum(hist[i0] > 0))
    members = [isa_label(j) for j in cls[:5]]
    suffix = f" +{len(cls)-5} more" if len(cls) > 5 else ""
    print(f"{len(cls):>5} {omega:>8.4f} {entropy:>8.2f} {reach:>6}  {'; '.join(members)}{suffix}")

print(f"\n=== STRUCTURE OF EQUIVALENCE ===")
print("What makes two ISAs output-equivalent?\n")

for cls in classes[:5]:
    if len(cls) < 2:
        continue
    print(f"Class of size {len(cls)} (omega={halting[cls[0]]/1679616:.4f}):")
    op_sets = []
    for j in cls[:8]:
        o = [int(ops_arr[j, k]) for k in range(4)]
        op_sets.append(set(o))
        print(f"  {isa_label(j)}  ops={o}")
    if len(cls) > 8:
        print(f"  ... +{len(cls)-8} more")

    all_same_set = all(s == op_sets[0] for s in op_sets)
    if all_same_set and len(cls) > 1:
        print(f"  -> All members use the SAME opcode set {op_sets[0]} in different slot orders.")
        print(f"     This class is a permutation orbit of opcode ordering.")
    else:
        shared = set.intersection(*op_sets) if op_sets else set()
        print(f"  -> Shared opcodes across all members: {shared}")
    print()

print("=== PERMUTATION ORBITS ===")
print("How many classes consist entirely of opcode permutations?\n")

perm_classes = 0
non_perm_classes = 0
for cls in classes:
    if len(cls) < 2:
        continue
    op_sets = [frozenset(int(ops_arr[j, k]) for k in range(4)) for j in cls]
    if len(set(op_sets)) == 1:
        perm_classes += 1
    else:
        non_perm_classes += 1

print(f"Classes that are pure permutation orbits: {perm_classes}")
print(f"Classes with genuinely different opcode sets: {non_perm_classes}")

if non_perm_classes > 0:
    print(f"\nNon-permutation equivalences (different opcodes, same output):")
    shown = 0
    for cls in classes:
        if len(cls) < 2:
            continue
        op_sets = [frozenset(int(ops_arr[j, k]) for k in range(4)) for j in cls]
        unique_sets = set(op_sets)
        if len(unique_sets) > 1:
            if shown >= 5:
                break
            print(f"\n  Class size {len(cls)}, omega={halting[cls[0]]/1679616:.4f}:")
            for us in list(unique_sets)[:4]:
                example = next(j for j in cls if frozenset(int(ops_arr[j,k]) for k in range(4)) == us)
                print(f"    {isa_label(example)}  set={set(us)}")
            shown += 1

print(f"\n=== OMEGA EQUIVALENCE ===")
print("ISAs with identical omega but DIFFERENT output distributions:\n")

omega_groups = defaultdict(list)
for i in range(n_isas):
    omega_groups[halting[i]].append(i)

omega_same_output_diff = 0
for halt_count, members in omega_groups.items():
    if len(members) < 2:
        continue
    fps = set()
    for m in members:
        fps.add(tuple(hist[m].tolist()))
    if len(fps) > 1:
        omega_same_output_diff += 1

print(f"Omega values with multiple distinct output distributions: {omega_same_output_diff}")
print(f"(Same halting count, different outputs — omega doesn't determine P(x))")

results = {
    "n_classes": n_classes,
    "n_multi": sum(1 for s in sizes if s > 1),
    "largest_class": sizes[0],
    "singletons": sum(1 for s in sizes if s == 1),
    "perm_orbit_classes": perm_classes,
    "non_perm_classes": non_perm_classes,
    "omega_same_output_diff": omega_same_output_diff,
    "size_distribution": dict(size_counts),
}
with open("experiments/kolmogorov-omega/isa_equivalence.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nWrote isa_equivalence.json")
