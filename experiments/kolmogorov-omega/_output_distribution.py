#!/usr/bin/env python3
"""Output distribution tensor + K(x) ranking.

For each of 38,416 ISAs, compute the full 256-bin output histogram
of halting programs and track the smallest program index producing
each output. Parallelized across all CPU cores.

Produces:
  output_tensor.npz  — hist(38416,256), k_prog(38416,256), ops(38416,4)
  output_summary.json — per-ISA entropy, reachable count, top outputs
"""
import numba
import numpy as np
import time
import json
import multiprocessing
import os
import sys

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
def compute_output_dist(ops):
    hist = np.zeros(256, dtype=np.int64)
    k_prog = np.full(256, -1, dtype=np.int64)
    halts = 0
    for prog in range(SPACE):
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
                a, b = apply_op(ops[opcode], a, b)
                pc += 1
        if halted:
            halts += 1
            hist[a] += 1
            if k_prog[a] == -1:
                k_prog[a] = prog
    return halts, hist, k_prog

OP_IDS = [0,1,2,3,4,6,7,8,9,10,11,12,13,14]

def warmup():
    ops = np.array([0,1,2,3,4], dtype=np.int32)
    compute_output_dist(ops)

def process_chunk(chunk):
    results = []
    for o1, o2, o3, o4 in chunk:
        ops = np.array([0, o1, o2, o3, o4], dtype=np.int32)
        h, hist, k_prog = compute_output_dist(ops)
        results.append((o1, o2, o3, o4, int(h), hist.copy(), k_prog.copy()))
    return results

def main():
    print("JIT warmup...", flush=True)
    warmup()
    print("Ready.", flush=True)

    all_isas = [(o1,o2,o3,o4) for o1 in OP_IDS for o2 in OP_IDS for o3 in OP_IDS for o4 in OP_IDS]
    total = len(all_isas)
    ncpu = os.cpu_count() or 4
    chunk_size = max(1, total // (ncpu * 4))
    chunks = [all_isas[i:i+chunk_size] for i in range(0, total, chunk_size)]
    print(f"ISAs: {total}, CPUs: {ncpu}, chunks: {len(chunks)} x ~{chunk_size}", flush=True)

    ops_arr = np.zeros((total, 4), dtype=np.int32)
    hist_arr = np.zeros((total, 256), dtype=np.int64)
    kprog_arr = np.full((total, 256), -1, dtype=np.int64)
    halt_arr = np.zeros(total, dtype=np.int64)

    t_start = time.perf_counter()
    idx = 0
    with multiprocessing.Pool(ncpu, initializer=warmup) as pool:
        for chunk_result in pool.imap_unordered(process_chunk, chunks):
            for o1, o2, o3, o4, h, hist, k_prog in chunk_result:
                row = None
                for r in range(total):
                    if ops_arr[r,0] == 0 and halt_arr[r] == 0 and r >= idx:
                        row = r
                        break
                if row is None:
                    row = idx
                ops_arr[idx] = [o1, o2, o3, o4]
                hist_arr[idx] = hist
                kprog_arr[idx] = k_prog
                halt_arr[idx] = h
                idx += 1
            done = idx
            if done % 2000 < chunk_size + 50:
                elapsed = time.perf_counter() - t_start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate / 60 if rate > 0 else 0
                print(f"  {done}/{total} ({done*100//total}%) {rate:.0f} ISA/s ETA {eta:.1f}m", flush=True)

    elapsed = time.perf_counter() - t_start
    print(f"Done: {idx} ISAs in {elapsed/60:.1f} minutes", flush=True)

    sort_idx = np.lexsort((ops_arr[:,3], ops_arr[:,2], ops_arr[:,1], ops_arr[:,0]))
    ops_arr = ops_arr[sort_idx]
    hist_arr = hist_arr[sort_idx]
    kprog_arr = kprog_arr[sort_idx]
    halt_arr = halt_arr[sort_idx]

    np.savez_compressed("output_tensor.npz",
                        ops=ops_arr, hist=hist_arr, k_prog=kprog_arr, halting=halt_arr)
    fsize = os.path.getsize("output_tensor.npz")
    print(f"Wrote output_tensor.npz ({fsize/1024/1024:.1f} MB)", flush=True)

    summary = []
    for i in range(len(ops_arr)):
        h = hist_arr[i]
        halts = halt_arr[i]
        if halts == 0:
            continue
        p = h / halts
        p_nz = p[p > 0]
        entropy = -float(np.sum(p_nz * np.log2(p_nz)))
        reachable = int(np.sum(h > 0))
        top_outputs = sorted(
            [(int(x), int(h[x])) for x in range(256) if h[x] > 0],
            key=lambda t: -t[1]
        )[:5]
        summary.append({
            "op1": int(ops_arr[i,0]), "op2": int(ops_arr[i,1]),
            "op3": int(ops_arr[i,2]), "op4": int(ops_arr[i,3]),
            "halting": int(halts),
            "reachable_outputs": reachable,
            "entropy_bits": round(entropy, 4),
            "top_outputs": top_outputs,
        })
    with open("output_summary.json", "w") as f:
        json.dump(summary, f)
    print(f"Wrote output_summary.json ({len(summary)} entries)", flush=True)

    entropies = [s["entropy_bits"] for s in summary]
    reachables = [s["reachable_outputs"] for s in summary]
    print(f"\nEntropy: min={min(entropies):.2f} max={max(entropies):.2f} mean={sum(entropies)/len(entropies):.2f} bits")
    print(f"Reachable outputs: min={min(reachables)} max={max(reachables)} mean={sum(reachables)/len(reachables):.1f} / 256")

    zero_counts = np.sum(hist_arr, axis=0)
    universally_reachable = int(np.sum(zero_counts == 0))
    always_reachable = int(np.sum(np.all(hist_arr > 0, axis=0)))
    print(f"Outputs reachable by ALL ISAs: {always_reachable}")
    print(f"Outputs reachable by NO ISA: {universally_reachable}")

if __name__ == "__main__":
    main()
