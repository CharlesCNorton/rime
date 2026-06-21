#!/usr/bin/env python3
"""Width scaling to W=20 for 5 ISAs. Exhaustive enumeration."""
import numba
import numpy as np
import time
import json

SPACE = 1679616  # 6^8
N = 8

@numba.njit
def apply_op(op_id, a, b, mask):
    if op_id == 0: return (a + 1) & mask, b
    elif op_id == 1: return (a - 1) & mask, b
    elif op_id == 2: return b, a
    elif op_id == 3: return (a + b) & mask, b
    elif op_id == 4: return a ^ b, b
    elif op_id == 6: return (-a) & mask, b
    elif op_id == 7: return a, a
    elif op_id == 8: return (a - b) & mask, b
    elif op_id == 9: return a & b, b
    elif op_id == 10: return a | b, b
    elif op_id == 11: return a >> 1, b
    elif op_id == 12: return (a << 1) & mask, b
    elif op_id == 13: return (~a) & mask, b
    else: return a, b

@numba.njit
def count_halting_w(ops, t_max, mask):
    halts = 0
    for prog in range(SPACE):
        tmp = prog
        p = np.empty(N, dtype=np.int32)
        for i in range(N):
            p[i] = tmp % 6
            tmp //= 6
        a, b, pc = 0, 0, 0
        halted = False
        for step in range(t_max):
            if pc >= N:
                halted = True
                break
            opcode = p[pc]
            if opcode == 5:
                if a != 0:
                    pc = 0
                else:
                    pc += 1
            else:
                a, b = apply_op(ops[opcode], a, b, mask)
                pc += 1
        if halted:
            halts += 1
    return halts

# ISAs to test
ISAS = {
    "A":    np.array([0, 1, 2, 3, 4], dtype=np.int32),   # INC DEC SWP ADD XOR
    "B":    np.array([0, 6, 7, 8, 9], dtype=np.int32),   # INC NEG MOV SUB AND
    "G":    np.array([0, 11, 7, 8, 9], dtype=np.int32),  # INC SHR MOV SUB AND
    "MIN":  np.array([0, 0, 0, 0, 0], dtype=np.int32),   # INC INC INC INC INC
    "MAX":  np.array([0, 9, 9, 9, 9], dtype=np.int32),   # INC AND AND AND AND
}

# Warmup
print("JIT warmup...")
ops = ISAS["A"]
_ = count_halting_w(ops, 256, 0xFF)
print("Ready.")
print()

WIDTHS = [8, 10, 12, 14, 16, 18, 20]

print(f"{'W':>4s}", end="")
for name in ISAS:
    print(f"  {name:>10s}", end="")
print(f"  {'D(A-B)':>10s}  {'Time':>8s}")
print("-" * 80)

results = {}
for W in WIDTHS:
    mask = (1 << W) - 1
    t_max = min(1 << W, 1 << 20)  # cap at 1M steps
    t0 = time.perf_counter()
    row = {}
    for name, ops in ISAS.items():
        h = count_halting_w(ops, t_max, mask)
        row[name] = h / SPACE
    elapsed = time.perf_counter() - t0
    delta_ab = row["A"] - row["B"]
    results[W] = row
    print(f"{W:4d}", end="")
    for name in ISAS:
        print(f"  {row[name]:10.6f}", end="")
    print(f"  {delta_ab:+10.6f}  {elapsed:7.1f}s")

# Summary
print()
deltas = [results[W]["A"] - results[W]["B"] for W in WIDTHS]
import statistics
print(f"Delta(A-B) mean: {statistics.mean(deltas):.6f}")
print(f"Delta(A-B) stdev: {statistics.stdev(deltas):.6f}")
print(f"Delta(A-B) CV: {abs(statistics.stdev(deltas)/statistics.mean(deltas))*100:.2f}%")

# Save
with open("experiments/kolmogorov-omega/width_scaling.json", "w") as f:
    json.dump(results, f, indent=2)
print("Wrote width_scaling.json")
