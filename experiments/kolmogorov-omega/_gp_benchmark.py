#!/usr/bin/env python3
"""GP benchmark: program synthesis efficiency vs halting fraction.

For each of 50 ISAs, run a simple genetic programming search for a
target function and measure generations to solution. Tests whether
ISA selection is a tunable hyperparameter for program synthesis.

Target: compute f(x) = (x + 1) mod 256 (the INC function).
The GP system generates random programs, evaluates them on 16 test
inputs, selects for fitness (number of correct outputs), and mutates.

Each ISA is tested with 100 independent GP runs. The median
generations-to-solution is compared against the ISA's omega.
"""
import numba
import numpy as np
import time
import json
import os

N = 8
T_MAX = 256

@numba.njit
def apply_op(op_id, a, b):
    if op_id == 0: return (a+1)&0xFF, b
    elif op_id == 1: return (a-1)&0xFF, b
    elif op_id == 2: return b, a
    elif op_id == 3: return (a+b)&0xFF, b
    elif op_id == 4: return a^b, b
    elif op_id == 6: return (-a)&0xFF, b
    elif op_id == 7: return a, a
    elif op_id == 8: return (a-b)&0xFF, b
    elif op_id == 9: return a&b, b
    elif op_id == 10: return a|b, b
    elif op_id == 11: return a>>1, b
    elif op_id == 12: return (a<<1)&0xFF, b
    elif op_id == 13: return (~a)&0xFF, b
    else: return a, b

@numba.njit
def execute(prog, ops, init_a):
    a, b, pc = init_a, 0, 0
    for step in range(T_MAX):
        if pc >= N:
            return a, True
        opcode = prog[pc]
        if opcode == 5:
            if a != 0: pc = 0
            else: pc += 1
        else:
            a, b = apply_op(ops[opcode], a, b)
            pc += 1
    return a, False

@numba.njit
def fitness(prog, ops, test_inputs, test_outputs):
    score = 0
    for i in range(len(test_inputs)):
        result, halted = execute(prog, ops, test_inputs[i])
        if halted and result == test_outputs[i]:
            score += 1
    return score

@numba.njit
def xorshift(s):
    s ^= numba.int64((s << 13) & 0xFFFFFFFF)
    s ^= numba.int64(s >> 17)
    s ^= numba.int64((s << 5) & 0xFFFFFFFF)
    return s & 0xFFFFFFFF

@numba.njit
def mutate(prog, rng_state):
    new_prog = prog.copy()
    rng_state = xorshift(rng_state)
    pos = rng_state % N
    rng_state = xorshift(rng_state)
    new_prog[pos] = rng_state % 6
    return new_prog, rng_state

@numba.njit
def gp_run(ops, test_inputs, test_outputs, pop_size, max_gens, seed):
    n_tests = len(test_inputs)
    rng = numba.int64(((seed + 1) * 2654435761) & 0xFFFFFFFF)

    pop = np.empty((pop_size, N), dtype=np.int32)
    for i in range(pop_size):
        for j in range(N):
            rng = xorshift(rng)
            pop[i, j] = rng % 6

    for gen in range(max_gens):
        scores = np.empty(pop_size, dtype=np.int32)
        for i in range(pop_size):
            scores[i] = fitness(pop[i], ops, test_inputs, test_outputs)
            if scores[i] == n_tests:
                return gen

        new_pop = np.empty((pop_size, N), dtype=np.int32)
        for i in range(pop_size):
            rng = xorshift(rng)
            p1 = rng % pop_size
            rng = xorshift(rng)
            p2 = rng % pop_size
            parent = p1 if scores[p1] >= scores[p2] else p2
            child, rng = mutate(pop[parent], rng)
            new_pop[i] = child
        pop = new_pop

    return max_gens

ISAS = {
    "A":   [0,1,2,3,4],
    "B":   [0,6,7,8,9],
    "C":   [0,11,13,3,10],
    "D":   [0,12,7,3,10],
    "E":   [0,6,2,13,4],
    "F":   [0,1,2,8,4],
    "G":   [0,11,7,8,9],
    "X08": [0,4,2,3,9],
    "X11": [0,6,2,3,9],
    "X14": [0,4,2,8,9],
    "X17": [0,6,2,8,9],
    "X20": [0,4,2,3,11],
    "X23": [0,6,2,3,11],
    "X26": [0,4,2,8,11],
    "X29": [0,6,2,8,11],
    "X32": [0,4,2,3,1],
    "X35": [0,6,2,3,1],
    "X38": [0,4,2,8,1],
    "X41": [0,6,2,8,1],
    "X44": [0,4,7,3,9],
    "X47": [0,6,7,3,9],
    "X50": [0,4,7,8,9],
    "MIN": [0,0,0,0,0],
    "MAX": [0,9,9,9,9],
}

KNOWN_OMEGAS = {}

def main():
    import pandas as pd
    tensor_path = os.path.join(os.path.dirname(__file__) or ".", "omega_tensor.parquet")
    if os.path.exists(tensor_path):
        tdf = pd.read_parquet(tensor_path)
        for _, row in tdf.iterrows():
            key = (int(row.op1), int(row.op2), int(row.op3), int(row.op4))
            KNOWN_OMEGAS[key] = float(row.omega)

    test_inputs = np.array([0, 1, 2, 15, 16, 42, 100, 127, 128, 200, 250, 254, 255, 3, 7, 63], dtype=np.int32)
    test_outputs = np.array([(x + 1) & 0xFF for x in test_inputs], dtype=np.int32)

    pop_size = 200
    max_gens = 5000
    n_trials = 100

    print("JIT warmup...", flush=True)
    ops = np.array([0,1,2,3,4], dtype=np.int32)
    gp_run(ops, test_inputs, test_outputs, 20, 10, 42)
    print("Ready.", flush=True)

    print(f"\nTarget: f(x) = (x+1) mod 256", flush=True)
    print(f"Pop: {pop_size}, Max gens: {max_gens}, Trials: {n_trials}", flush=True)
    print(f"Test inputs: {len(test_inputs)}", flush=True)
    print(flush=True)
    print(f"{'ISA':<6} {'Omega':>8} {'Median':>8} {'Mean':>8} {'Solved':>7} {'Min':>6} {'Max':>6}", flush=True)
    print("-" * 55, flush=True)

    results = []
    for name, op_list in sorted(ISAS.items(), key=lambda x: x[0]):
        ops = np.array(op_list, dtype=np.int32)
        key = tuple(op_list)
        omega = KNOWN_OMEGAS.get(key, 0.0)

        gens_list = []
        for trial in range(n_trials):
            g = gp_run(ops, test_inputs, test_outputs, pop_size, max_gens, trial * 7 + 13)
            gens_list.append(g)

        gens_arr = np.array(gens_list)
        solved = int(np.sum(gens_arr < max_gens))
        median = int(np.median(gens_arr))
        mean = float(np.mean(gens_arr))
        mn = int(np.min(gens_arr))
        mx = int(np.max(gens_arr))

        print(f"{name:<6} {omega:>8.4f} {median:>8d} {mean:>8.1f} {solved:>5d}/{n_trials} {mn:>6d} {mx:>6d}", flush=True)

        results.append({
            "isa": name,
            "ops": op_list,
            "omega": omega,
            "median_gens": median,
            "mean_gens": round(mean, 1),
            "solved": solved,
            "min_gens": mn,
            "max_gens_seen": mx,
        })

    with open("gp_benchmark.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote gp_benchmark.json ({len(results)} ISAs)", flush=True)

    omegas = [r["omega"] for r in results if r["omega"] > 0 and r["solved"] > 0]
    medians = [r["median_gens"] for r in results if r["omega"] > 0 and r["solved"] > 0]
    if len(omegas) > 2:
        n = len(omegas)
        mo = sum(omegas)/n; mm = sum(medians)/n
        cov = sum((o-mo)*(m-mm) for o,m in zip(omegas, medians))/n
        so = (sum((o-mo)**2 for o in omegas)/n)**0.5
        sm = (sum((m-mm)**2 for m in medians)/n)**0.5
        r = cov/(so*sm) if so*sm > 0 else 0
        print(f"\nPearson r(omega, median_gens) = {r:.4f}")

if __name__ == "__main__":
    main()
