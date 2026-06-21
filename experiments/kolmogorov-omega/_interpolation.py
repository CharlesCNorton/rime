#!/usr/bin/env python3
"""Phase transition test: interpolate between two ISAs.

At each program step, a PRNG seeded by (program_index, step) selects
ISA-A's opcode with probability T, ISA-B's with probability 1-T.
Sweep T from 0 to 1 in 101 steps. Exhaustive enumeration at each T.

If the stat-mech analogy holds, Omega(T) is smooth.
A kink or discontinuity indicates critical behavior in program space.
"""
import numba
import numpy as np
import time
import json
import multiprocessing
import os

SPACE = 1679616
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
def xorshift32(state):
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= (state >> 17)
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF

@numba.njit
def count_halting_interp(ops_a, ops_b, t_frac_num, t_frac_den):
    halts = 0
    for prog in range(SPACE):
        tmp = prog
        p = np.empty(N, dtype=np.int32)
        for i in range(N):
            p[i] = tmp % 6; tmp //= 6
        a, b, pc = 0, 0, 0
        halted = False
        rng = np.uint32((prog + 1) * np.uint32(2654435761))
        for step in range(T_MAX):
            if pc >= N:
                halted = True; break
            opcode = p[pc]
            if opcode == 5:
                if a != 0: pc = 0
                else: pc += 1
            else:
                rng = xorshift32(rng)
                if (rng % t_frac_den) < t_frac_num:
                    a, b = apply_op(ops_a[opcode], a, b)
                else:
                    a, b = apply_op(ops_b[opcode], a, b)
                pc += 1
        if halted:
            halts += 1
    return halts

ISA_A = np.array([0, 1, 2, 3, 4], dtype=np.int32)
ISA_B = np.array([0, 6, 7, 8, 9], dtype=np.int32)

def warmup():
    count_halting_interp(ISA_A, ISA_B, np.uint32(50), np.uint32(100))

def process_t(args):
    t_idx, t_num, t_den = args
    h = count_halting_interp(ISA_A, ISA_B, np.uint32(t_num), np.uint32(t_den))
    return t_idx, t_num, t_den, int(h)

def main():
    print("JIT warmup...", flush=True)
    warmup()
    print("Ready.", flush=True)

    n_steps = 101
    tasks = [(i, i, n_steps - 1) for i in range(n_steps)]
    ncpu = os.cpu_count() or 4
    print(f"Interpolation: {n_steps} values of T, CPUs: {ncpu}", flush=True)
    print(f"ISA-A: INC DEC SWP ADD XOR", flush=True)
    print(f"ISA-B: INC NEG MOV SUB AND", flush=True)

    t_start = time.perf_counter()
    results = [None] * n_steps
    done = 0
    with multiprocessing.Pool(ncpu, initializer=warmup) as pool:
        for t_idx, t_num, t_den, h in pool.imap_unordered(process_t, tasks):
            t_val = t_num / t_den if t_den > 0 else 0
            omega = h / SPACE
            results[t_idx] = {"t_idx": t_idx, "t": round(t_val, 4), "halting": h, "omega": round(omega, 6)}
            done += 1
            elapsed = time.perf_counter() - t_start
            rate = done / elapsed
            eta = (n_steps - done) / rate / 60 if rate > 0 else 0
            print(f"  T={t_val:.4f}  omega={omega:.6f}  ({done}/{n_steps}, ETA {eta:.1f}m)", flush=True)

    elapsed = time.perf_counter() - t_start
    print(f"\nDone in {elapsed/60:.1f} minutes", flush=True)

    with open("interpolation.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Wrote interpolation.json", flush=True)

    omegas = [r["omega"] for r in results]
    print(f"\nOmega(T=0) = {omegas[0]:.6f}  (pure ISA-B)")
    print(f"Omega(T=1) = {omegas[-1]:.6f}  (pure ISA-A)")
    print(f"Range: [{min(omegas):.6f}, {max(omegas):.6f}]")

    diffs = [abs(omegas[i+1] - omegas[i]) for i in range(len(omegas)-1)]
    max_jump = max(diffs)
    max_jump_idx = diffs.index(max_jump)
    mean_jump = sum(diffs) / len(diffs)
    print(f"Max consecutive jump: {max_jump:.6f} at T={results[max_jump_idx]['t']:.4f}")
    print(f"Mean consecutive jump: {mean_jump:.6f}")
    print(f"Ratio max/mean: {max_jump/mean_jump:.2f}")

    if max_jump / mean_jump > 5:
        print("RESULT: Possible phase transition detected.")
    else:
        print("RESULT: Smooth interpolation. Stat-mech analogy supported.")

if __name__ == "__main__":
    main()
