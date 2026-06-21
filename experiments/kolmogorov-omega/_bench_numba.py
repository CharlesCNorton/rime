#!/usr/bin/env python3
"""Numba-accelerated exhaustive Omega computation for all 38,416 ISAs."""
import numba
import numpy as np
import time
import json

SPACE = 1679616  # 6^8
N = 8
T_MAX = 256

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
    else: return a, b  # NOP (14)

@numba.njit
def count_halting(ops):
    """Count halting programs for ISA defined by ops[0..4] (opcode 0-4 operation IDs)."""
    halts = 0
    for prog in range(SPACE):
        tmp = prog
        p = np.empty(N, dtype=np.int32)
        for i in range(N):
            p[i] = tmp % 6
            tmp //= 6
        a, b, pc = 0, 0, 0
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

if __name__ == "__main__":
    # Warmup
    print("JIT compiling...")
    ops = np.array([0, 1, 2, 3, 4], dtype=np.int32)  # ISA-A
    t0 = time.perf_counter()
    h = count_halting(ops)
    compile_time = time.perf_counter() - t0
    print(f"Compile + run: {compile_time:.1f}s, ISA-A halts={h} (expect 978929)")

    # Benchmark
    t0 = time.perf_counter()
    h = count_halting(ops)
    run_time = time.perf_counter() - t0
    print(f"Run only: {run_time:.2f}s, halts={h}")

    OP_IDS = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    total = len(OP_IDS) ** 4
    print(f"Total ISAs: {total}")
    print(f"Projected time: {total * run_time / 3600:.1f} hours")
    print(f"Per ISA: {run_time:.2f}s")

    import sys
    if "--full" in sys.argv:
        OP_NAMES = {0:"INC",1:"DEC",2:"SWP",3:"ADD",4:"XOR",6:"NEG",7:"MOV",
                    8:"SUB",9:"AND",10:"OR",11:"SHR",12:"SHL",13:"CPL",14:"NOP"}
        results = []
        done = 0
        t_start = time.perf_counter()
        for o1 in OP_IDS:
            for o2 in OP_IDS:
                for o3 in OP_IDS:
                    for o4 in OP_IDS:
                        ops = np.array([0, o1, o2, o3, o4], dtype=np.int32)
                        h = count_halting(ops)
                        results.append({
                            "op1": o1, "op2": o2, "op3": o3, "op4": o4,
                            "op1_name": OP_NAMES[o1], "op2_name": OP_NAMES[o2],
                            "op3_name": OP_NAMES[o3], "op4_name": OP_NAMES[o4],
                            "halting_count": int(h),
                            "omega": h / SPACE,
                        })
                        done += 1
                        if done % 1000 == 0:
                            elapsed = time.perf_counter() - t_start
                            eta = elapsed / done * (total - done) / 3600
                            print(f"  {done}/{total} ({done*100//total}%) ETA {eta:.1f}h")
        elapsed = time.perf_counter() - t_start
        print(f"Done: {done} ISAs in {elapsed/3600:.1f} hours")
        with open("omega_tensor.json", "w") as f:
            json.dump(results, f)
        print(f"Wrote omega_tensor.json ({len(results)} entries)")
