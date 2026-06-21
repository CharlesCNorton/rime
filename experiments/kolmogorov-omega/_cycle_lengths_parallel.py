#!/usr/bin/env python3
"""Cycle length tensor — parallelized across all CPU cores."""
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
def compute_cycle_stats(ops):
    halts = 0
    nonhalt = 0
    cycle_sum = 0
    cycle_max = 0
    for prog in range(SPACE):
        tmp = prog
        p = np.empty(N, dtype=np.int32)
        for i in range(N):
            p[i] = tmp % 6; tmp //= 6
        a, b, pc = 0, 0, 0
        states_a = np.empty(T_MAX+1, dtype=np.int32)
        states_b = np.empty(T_MAX+1, dtype=np.int32)
        states_pc = np.empty(T_MAX+1, dtype=np.int32)
        halted = False
        step = 0
        for step in range(T_MAX):
            states_a[step] = a
            states_b[step] = b
            states_pc[step] = pc
            if pc >= N:
                halted = True; break
            opcode = p[pc]
            if opcode == 5:
                if a != 0: pc = 0
                else: pc += 1
            else:
                a, b = apply_op(ops[opcode], a, b)
                pc += 1
        if halted:
            halts += 1
        else:
            nonhalt += 1
            final_a, final_b, final_pc = a, b, pc
            cycle_len = 0
            for back in range(1, step+1):
                if states_a[step-back] == final_a and states_b[step-back] == final_b and states_pc[step-back] == final_pc:
                    cycle_len = back
                    break
            if cycle_len == 0:
                cycle_len = step
            cycle_sum += cycle_len
            if cycle_len > cycle_max:
                cycle_max = cycle_len
    return halts, nonhalt, cycle_sum, cycle_max

OP_IDS = [0,1,2,3,4,6,7,8,9,10,11,12,13,14]

def warmup():
    ops = np.array([0,1,2,3,4], dtype=np.int32)
    compute_cycle_stats(ops)

def process_chunk(chunk):
    results = []
    for o1, o2, o3, o4 in chunk:
        ops = np.array([0, o1, o2, o3, o4], dtype=np.int32)
        h, nh, cs, cm = compute_cycle_stats(ops)
        avg_cycle = cs/nh if nh > 0 else 0
        results.append({
            "op1":o1,"op2":o2,"op3":o3,"op4":o4,
            "halting":int(h),"nonhalting":int(nh),
            "avg_cycle":round(avg_cycle,2),"max_cycle":int(cm),
        })
    return results

def main():
    print("JIT warmup...")
    warmup()
    print("Ready.")

    all_isas = [(o1,o2,o3,o4) for o1 in OP_IDS for o2 in OP_IDS for o3 in OP_IDS for o4 in OP_IDS]
    total = len(all_isas)
    ncpu = os.cpu_count() or 4
    chunk_size = max(1, total // (ncpu * 4))
    chunks = [all_isas[i:i+chunk_size] for i in range(0, total, chunk_size)]

    print(f"ISAs: {total}, CPUs: {ncpu}, chunks: {len(chunks)} x ~{chunk_size}")

    t_start = time.perf_counter()
    results = []
    with multiprocessing.Pool(ncpu, initializer=warmup) as pool:
        for i, chunk_result in enumerate(pool.imap_unordered(process_chunk, chunks)):
            results.extend(chunk_result)
            done = len(results)
            if done % 2000 < chunk_size:
                elapsed = time.perf_counter() - t_start
                rate = done / elapsed
                eta = (total - done) / rate / 60 if rate > 0 else 0
                print(f"  {done}/{total} ({done*100//total}%) {rate:.0f} ISA/s ETA {eta:.1f}m")

    elapsed = time.perf_counter() - t_start
    print(f"Done: {len(results)} ISAs in {elapsed/60:.1f} minutes ({elapsed/3600:.2f} hours)")

    results.sort(key=lambda r: (r["op1"], r["op2"], r["op3"], r["op4"]))
    with open("cycle_tensor.json", "w") as f:
        json.dump(results, f)
    print(f"Wrote cycle_tensor.json ({len(results)} entries)")

if __name__ == "__main__":
    main()
