#!/usr/bin/env python3
import numba
import numpy as np
import time
import json

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
    cycle_hist = np.zeros(257, dtype=np.int64)
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
            if cycle_len < 257:
                cycle_hist[cycle_len] += 1
    return halts, nonhalt, cycle_sum, cycle_max, cycle_hist

OP_IDS = [0,1,2,3,4,6,7,8,9,10,11,12,13,14]
OP_NAMES = {0:'INC',1:'DEC',2:'SWP',3:'ADD',4:'XOR',6:'NEG',7:'MOV',
            8:'SUB',9:'AND',10:'OR',11:'SHR',12:'SHL',13:'CPL',14:'NOP'}

print("JIT warmup...")
ops = np.array([0,1,2,3,4], dtype=np.int32)
_ = compute_cycle_stats(ops)
print("Ready.")
print()

import sys
if "--full" in sys.argv:
    total = len(OP_IDS)**4
    results = []
    done = 0
    t_start = time.perf_counter()
    for o1 in OP_IDS:
        for o2 in OP_IDS:
            for o3 in OP_IDS:
                for o4 in OP_IDS:
                    ops = np.array([0,o1,o2,o3,o4], dtype=np.int32)
                    h, nh, cs, cm, ch = compute_cycle_stats(ops)
                    avg_cycle = cs/nh if nh > 0 else 0
                    results.append({
                        "op1":o1,"op2":o2,"op3":o3,"op4":o4,
                        "halting":int(h),"nonhalting":int(nh),
                        "avg_cycle":round(avg_cycle,2),"max_cycle":int(cm),
                    })
                    done += 1
                    if done % 1000 == 0:
                        elapsed = time.perf_counter() - t_start
                        eta = elapsed/done*(total-done)/3600
                        print(f"  {done}/{total} ({done*100//total}%) ETA {eta:.1f}h")
    elapsed = time.perf_counter() - t_start
    print(f"Done: {done} ISAs in {elapsed/3600:.1f} hours")
    with open("experiments/kolmogorov-omega/cycle_tensor.json","w") as f:
        json.dump(results, f)
    print("Wrote cycle_tensor.json")
else:
    print("Sample: 5 ISAs")
    for name, op_list in [("A",[0,1,2,3,4]),("B",[0,6,7,8,9]),("G",[0,11,7,8,9]),
                           ("MIN",[0,0,0,0,0]),("MAX",[0,9,9,9,9])]:
        ops = np.array(op_list, dtype=np.int32)
        t0 = time.perf_counter()
        h, nh, cs, cm, ch = compute_cycle_stats(ops)
        elapsed = time.perf_counter() - t0
        avg = cs/nh if nh > 0 else 0
        print(f"  {name:>4s}: halt={h:>7d} nonhalt={nh:>7d} avg_cycle={avg:6.1f} max_cycle={cm:>4d} ({elapsed:.1f}s)")
        top_cycles = [(i, int(ch[i])) for i in range(257) if ch[i] > 0]
        top_cycles.sort(key=lambda x: -x[1])
        top3 = top_cycles[:5]
        print(f"        top cycles: {top3}")
