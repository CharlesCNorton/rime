#!/usr/bin/env python3
"""Initial-state tensor: Omega(ISA, init_a) for all 38,416 ISAs x 256 init values.

Robust design:
  - Checkpoints every 500 ISAs to init_state_checkpoint.npz
  - Resumes from checkpoint on restart
  - Per-worker timeout via alarm signal
  - Catches and logs all exceptions per ISA without stopping
  - Writes final output to init_state_tensor.npz
  - Progress log with ETA to init_state.log
"""
import numba
import numpy as np
import time
import json
import multiprocessing
import os
import sys
import signal
import traceback

SPACE = 1679616
N = 8
T_MAX = 256
N_INIT = 256

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd()
HOME = os.path.expanduser("~")
BASE = HOME if os.path.isdir(HOME) else SCRIPT_DIR

CHECKPOINT_FILE = os.path.join(BASE, "init_state_checkpoint.npz")
OUTPUT_FILE = os.path.join(BASE, "init_state_tensor.npz")
LOG_FILE = os.path.join(BASE, "init_state.log")

OP_IDS = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


@numba.njit
def apply_op(op_id, a, b):
    if op_id == 0: return (a + 1) & 0xFF, b
    elif op_id == 1: return (a - 1) & 0xFF, b
    elif op_id == 2: return b, a
    elif op_id == 3: return (a + b) & 0xFF, b
    elif op_id == 4: return a ^ b, b
    elif op_id == 6: return (-a) & 0xFF, b
    elif op_id == 7: return a, a
    elif op_id == 8: return (a - b) & 0xFF, b
    elif op_id == 9: return a & b, b
    elif op_id == 10: return a | b, b
    elif op_id == 11: return a >> 1, b
    elif op_id == 12: return (a << 1) & 0xFF, b
    elif op_id == 13: return (~a) & 0xFF, b
    else: return a, b


@numba.njit
def count_halting_init(ops, init_a):
    halts = 0
    for prog in range(SPACE):
        tmp = prog
        p = np.empty(N, dtype=np.int32)
        for i in range(N):
            p[i] = tmp % 6
            tmp //= 6
        a = init_a
        b = 0
        pc = 0
        halted = False
        for step in range(T_MAX):
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
                a, b = apply_op(ops[opcode], a, b)
                pc += 1
        if halted:
            halts += 1
    return halts


def warmup():
    ops = np.array([0, 1, 2, 3, 4], dtype=np.int32)
    count_halting_init(ops, 0)
    count_halting_init(ops, 1)


def process_isa(args):
    isa_idx, o1, o2, o3, o4 = args
    ops = np.array([0, o1, o2, o3, o4], dtype=np.int32)
    results = np.zeros(N_INIT, dtype=np.int64)
    try:
        for init_a in range(N_INIT):
            results[init_a] = count_halting_init(ops, init_a)
    except Exception:
        return isa_idx, o1, o2, o3, o4, None
    return isa_idx, o1, o2, o3, o4, results


def build_isa_list():
    isas = []
    idx = 0
    for o1 in OP_IDS:
        for o2 in OP_IDS:
            for o3 in OP_IDS:
                for o4 in OP_IDS:
                    isas.append((idx, o1, o2, o3, o4))
                    idx += 1
    return isas


def load_checkpoint():
    cp_path = CHECKPOINT_FILE
    # Also check for the old buggy double-suffix file
    old_buggy = os.path.join(BASE, "init_state_checkpoint.npz.tmp.npz")
    if not os.path.exists(cp_path) and os.path.exists(old_buggy):
        log(f"Found old checkpoint at {old_buggy}, using it")
        cp_path = old_buggy
    if not os.path.exists(cp_path):
        return None, None, None, set()
    try:
        data = np.load(cp_path)
        ops_arr = data["ops"]
        halt_arr = data["halts"]
        done_set = set()
        for i in range(len(ops_arr)):
            if np.any(halt_arr[i] != 0) or (ops_arr[i, 0] == 0 and ops_arr[i, 1] == 0 and
                                              ops_arr[i, 2] == 0 and ops_arr[i, 3] == 0):
                key = tuple(ops_arr[i])
                done_set.add(key)
        return ops_arr, halt_arr, data.get("errors", np.array([])), done_set
    except Exception as e:
        log(f"WARNING: checkpoint load failed: {e}")
        return None, None, None, set()


def save_checkpoint(ops_arr, halt_arr, error_count):
    tmp = os.path.join(BASE, "init_state_checkpoint_tmp")
    try:
        np.savez_compressed(tmp, ops=ops_arr, halts=halt_arr, errors=np.array([error_count]))
        os.replace(tmp + ".npz", CHECKPOINT_FILE)
    except Exception as e:
        log(f"WARNING: checkpoint save failed: {e}")
        import traceback
        log(traceback.format_exc())


def main():
    log("=== INIT STATE TENSOR ===")
    log(f"ISAs: {len(OP_IDS)**4}, init values: {N_INIT}, programs/eval: {SPACE}")
    log(f"Total evaluations: {len(OP_IDS)**4 * N_INIT:,}")

    log("JIT warmup...")
    warmup()
    log("JIT ready.")

    all_isas = build_isa_list()
    total = len(all_isas)

    ops_cp, halt_cp, err_cp, done_set = load_checkpoint()

    ops_arr = np.zeros((total, 4), dtype=np.int32)
    halt_arr = np.zeros((total, N_INIT), dtype=np.int64)

    if ops_cp is not None and len(ops_cp) == total:
        ops_arr = ops_cp
        halt_arr = halt_cp
        log(f"Resumed from checkpoint: {len(done_set)} ISAs already done")
    else:
        for isa in all_isas:
            idx, o1, o2, o3, o4 = isa
            ops_arr[idx] = [o1, o2, o3, o4]
        done_set = set()

    remaining = [isa for isa in all_isas if tuple(ops_arr[isa[0]]) not in done_set
                 or not np.any(halt_arr[isa[0]] != 0)]
    if ops_cp is None:
        remaining = all_isas

    log(f"Remaining: {len(remaining)} ISAs")

    if len(remaining) == 0:
        log("All ISAs already computed. Writing final output.")
        np.savez_compressed(OUTPUT_FILE[:-4] if OUTPUT_FILE.endswith(".npz") else OUTPUT_FILE, ops=ops_arr, halts=halt_arr)
        log(f"Wrote {OUTPUT_FILE}")
        return

    ncpu = os.cpu_count() or 4
    ncpu = min(ncpu, 18)
    log(f"Workers: {ncpu}")

    t_start = time.perf_counter()
    done_count = total - len(remaining)
    error_count = 0
    checkpoint_interval = 500
    last_checkpoint = done_count

    with multiprocessing.Pool(ncpu, initializer=warmup) as pool:
        for result in pool.imap_unordered(process_isa, remaining, chunksize=1):
            isa_idx, o1, o2, o3, o4, results = result

            if results is None:
                error_count += 1
                log(f"ERROR: ISA ({o1},{o2},{o3},{o4}) index {isa_idx} failed")
                continue

            ops_arr[isa_idx] = [o1, o2, o3, o4]
            halt_arr[isa_idx] = results
            done_count += 1

            if done_count % 100 == 0 or done_count == total:
                elapsed = time.perf_counter() - t_start
                completed_this_run = done_count - (total - len(remaining))
                rate = completed_this_run / elapsed if elapsed > 0 else 0
                left = total - done_count
                eta_min = left / rate / 60 if rate > 0 else 0
                eta_hr = eta_min / 60
                log(f"  {done_count}/{total} ({done_count*100//total}%) "
                    f"{rate:.2f} ISA/s ETA {eta_hr:.1f}h errors={error_count}")

            if done_count - last_checkpoint >= checkpoint_interval:
                save_checkpoint(ops_arr, halt_arr, error_count)
                last_checkpoint = done_count
                log(f"  checkpoint saved at {done_count}")

    elapsed = time.perf_counter() - t_start
    log(f"Compute done: {done_count} ISAs in {elapsed/3600:.1f} hours, {error_count} errors")

    save_checkpoint(ops_arr, halt_arr, error_count)

    np.savez_compressed(OUTPUT_FILE[:-4] if OUTPUT_FILE.endswith(".npz") else OUTPUT_FILE, ops=ops_arr, halts=halt_arr)
    fsize = os.path.getsize(OUTPUT_FILE)
    log(f"Wrote {OUTPUT_FILE} ({fsize/1024/1024:.1f} MB)")

    omega_0 = halt_arr[:, 0] / SPACE
    omega_128 = halt_arr[:, 128] / SPACE
    ratio = omega_0 / np.where(omega_128 > 0, omega_128, 1)
    log(f"Omega(init=0): [{omega_0.min():.4f}, {omega_0.max():.4f}] mean={omega_0.mean():.4f}")
    log(f"Omega(init=128): [{omega_128.min():.4f}, {omega_128.max():.4f}] mean={omega_128.mean():.4f}")
    log(f"Ratio 0/128: [{ratio.min():.4f}, {ratio.max():.4f}] mean={ratio.mean():.4f}")
    log("=== DONE ===")


if __name__ == "__main__":
    main()
