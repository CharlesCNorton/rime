#!/usr/bin/env python3
"""Compute the composition semigroup size for each ISA at W=4.
State space: (A,B) in Z/16 x Z/16 = 256 states.
Each function table: 256 bytes. Full closure is tractable."""
import numba
import numpy as np
import pandas as pd
import time
import json

W = 4
MASK = (1 << W) - 1
STATE_SPACE = (1 << W) ** 2

SPACE_W4 = 1679616
N = 8
T_MAX = 1 << W

@numba.njit
def apply_op_w4(op_id, a, b):
    if op_id == 0: return (a+1)&MASK, b
    elif op_id == 1: return (a-1)&MASK, b
    elif op_id == 2: return b, a
    elif op_id == 3: return (a+b)&MASK, b
    elif op_id == 4: return a^b, b
    elif op_id == 6: return (-a)&MASK, b
    elif op_id == 7: return a, a
    elif op_id == 8: return (a-b)&MASK, b
    elif op_id == 9: return a&b, b
    elif op_id == 10: return a|b, b
    elif op_id == 11: return a>>1, b
    elif op_id == 12: return (a<<1)&MASK, b
    elif op_id == 13: return (~a)&MASK, b
    else: return a, b

@numba.njit
def make_table(op_id):
    t = np.empty(STATE_SPACE, dtype=np.int16)
    for s in range(STATE_SPACE):
        a = s >> W
        b = s & MASK
        a2, b2 = apply_op_w4(op_id, a, b)
        t[s] = np.int16((a2 << W) | b2)
    return t

@numba.njit
def compose(f, g):
    t = np.empty(STATE_SPACE, dtype=np.int16)
    for s in range(STATE_SPACE):
        t[s] = f[g[s]]
    return t

@numba.njit
def table_to_key(t):
    h = np.int64(0)
    for i in range(STATE_SPACE):
        h = h * np.int64(259) + np.int64(t[i])
        h = h & np.int64(0x7FFFFFFFFFFFFFFF)
    return h

def semigroup_closure(op_ids):
    generators = []
    for op_id in op_ids:
        generators.append(make_table(op_id))
    seen_keys = set()
    all_tables = []
    for g in generators:
        k = table_to_key(g)
        if k not in seen_keys:
            seen_keys.add(k)
            all_tables.append(g)
    frontier = list(all_tables)
    while frontier:
        new_frontier = []
        for f in frontier:
            for g in generators:
                fg = compose(f, g)
                k = table_to_key(fg)
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_tables.append(fg)
                    new_frontier.append(fg)
                gf = compose(g, f)
                k2 = table_to_key(gf)
                if k2 not in seen_keys:
                    seen_keys.add(k2)
                    all_tables.append(gf)
                    new_frontier.append(gf)
        frontier = new_frontier
        if len(seen_keys) > 500000:
            break
    return len(seen_keys)

@numba.njit
def count_halting_w4(ops):
    halts = 0
    for prog in range(SPACE_W4):
        tmp = prog
        p = np.empty(N, dtype=np.int32)
        for i in range(N):
            p[i] = tmp % 6; tmp //= 6
        a, b, pc = 0, 0, 0
        halted = False
        for step in range(T_MAX):
            if pc >= N:
                halted = True; break
            opcode = p[pc]
            if opcode == 5:
                if a != 0: pc = 0
                else: pc += 1
            else:
                a, b = apply_op_w4(ops[opcode], a, b)
                pc += 1
        if halted:
            halts += 1
    return halts

OP_IDS = [0,1,2,3,4,6,7,8,9,10,11,12,13,14]
OP_NAMES = {0:'INC',1:'DEC',2:'SWP',3:'ADD',4:'XOR',6:'NEG',7:'MOV',
            8:'SUB',9:'AND',10:'OR',11:'SHR',12:'SHL',13:'CPL',14:'NOP'}

def main():
    print(f"=== SEMIGROUP SIZE (W={W}, state space={STATE_SPACE}) ===", flush=True)

    print("JIT warmup...", flush=True)
    ops = np.array([0,1,2,3,4], dtype=np.int32)
    make_table(0)
    compose(make_table(0), make_table(1))
    table_to_key(make_table(0))
    count_halting_w4(ops)
    print("Ready.", flush=True)

    named_isas = [
        ("A", [0,1,2,3,4]),
        ("B", [0,6,7,8,9]),
        ("C", [0,11,13,3,10]),
        ("D", [0,12,7,3,10]),
        ("E", [0,6,2,13,4]),
        ("F", [0,1,2,8,4]),
        ("G", [0,11,7,8,9]),
        ("MIN", [0,0,0,0,0]),
        ("MAX", [0,9,9,9,9]),
    ]

    print(f"\n{'ISA':<6} {'Ops':<25} {'|S|':>8} {'Omega_4':>8} {'Omega_8':>8} {'Time':>6}", flush=True)
    print("-" * 70, flush=True)

    df = pd.read_parquet("experiments/kolmogorov-omega/omega_tensor.parquet")
    results = []

    for name, op_list in named_isas:
        ops = np.array(op_list, dtype=np.int32)
        row = df[(df.op1==op_list[1])&(df.op2==op_list[2])&(df.op3==op_list[3])&(df.op4==op_list[4])]
        omega_8 = float(row.iloc[0].omega) if len(row) > 0 else 0

        t0 = time.perf_counter()
        sg_size = semigroup_closure(op_list)
        elapsed_sg = time.perf_counter() - t0

        h4 = count_halting_w4(ops)
        omega_4 = h4 / SPACE_W4

        op_str = " ".join(OP_NAMES[o] for o in op_list)
        print(f"{name:<6} {op_str:<25} {sg_size:>8} {omega_4:>8.4f} {omega_8:>8.4f} {elapsed_sg:>5.1f}s", flush=True)
        results.append({"isa": name, "ops": op_list, "semigroup_size": sg_size,
                        "omega_w4": round(omega_4, 6), "omega_w8": omega_8})

    with open("experiments/kolmogorov-omega/semigroup_sizes.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote semigroup_sizes.json", flush=True)

    sizes = [r["semigroup_size"] for r in results]
    omegas = [r["omega_w8"] for r in results]
    n = len(sizes)
    ms = sum(sizes)/n; mo = sum(omegas)/n
    cov = sum((s-ms)*(o-mo) for s,o in zip(sizes,omegas))/n
    ss = (sum((s-ms)**2 for s in sizes)/n)**0.5
    so = (sum((o-mo)**2 for o in omegas)/n)**0.5
    r = cov/(ss*so) if ss*so > 0 else 0
    print(f"\nPearson r(|S|, omega_w8) = {r:.4f}")

    omegas4 = [r_["omega_w4"] for r_ in results]
    mo4 = sum(omegas4)/n
    cov4 = sum((s-ms)*(o-mo4) for s,o in zip(sizes,omegas4))/n
    so4 = (sum((o-mo4)**2 for o in omegas4)/n)**0.5
    r4 = cov4/(ss*so4) if ss*so4 > 0 else 0
    print(f"Pearson r(|S|, omega_w4) = {r4:.4f}")

if __name__ == "__main__":
    main()
