#!/usr/bin/env python3
"""Call/return stack depth sweep: depths 1 through 16."""
import numba
import numpy as np
import time

SPACE = 1679616
N = 8
T_MAX = 256

@numba.njit
def count_halting_call(stack_depth):
    halts = 0
    for prog in range(SPACE):
        tmp = prog
        p = np.empty(N, dtype=np.int32)
        for i in range(N):
            p[i] = tmp % 6
            tmp //= 6
        a, b, pc = 0, 0, 0
        ret_stack = np.zeros(stack_depth, dtype=np.int32)
        ret_sp = 0
        halted = False
        for step in range(T_MAX):
            if pc >= N:
                halted = True
                break
            opcode = p[pc]
            if opcode == 5:
                if a != 0:
                    ret_stack[ret_sp % stack_depth] = (pc + 1) % N
                    ret_sp += 1
                    pc = 0
                else:
                    pc += 1
            elif opcode == 4:
                if ret_sp > 0:
                    ret_sp -= 1
                    pc = ret_stack[ret_sp % stack_depth]
                else:
                    pc = 0
                    ret_sp = 0
            else:
                if opcode == 0:
                    a = (a + 1) & 0xFF
                elif opcode == 1:
                    a = (a - 1) & 0xFF
                elif opcode == 2:
                    a, b = b, a
                elif opcode == 3:
                    a = (a + b) & 0xFF
                pc += 1
        if halted:
            halts += 1
    return halts

print("JIT warmup...")
_ = count_halting_call(2)
print("Ready.")
print()

print(f"{'Depth':>6s}  {'Halting':>10s}  {'Omega':>10s}  {'Time':>8s}")
print("-" * 42)

results = {}
for depth in range(1, 17):
    t0 = time.perf_counter()
    h = count_halting_call(depth)
    elapsed = time.perf_counter() - t0
    omega = h / SPACE
    results[depth] = omega
    print(f"{depth:6d}  {h:10d}  {omega:10.6f}  {elapsed:7.1f}s")

print()

deltas = [results[d+1] - results[d] for d in range(1, 16)]
print("Delta between consecutive depths:")
for d in range(1, 16):
    print(f"  {d}->{d+1}: {deltas[d-1]:+.6f}")

import json
with open("experiments/kolmogorov-omega/stack_depth.json", "w") as f:
    json.dump(results, f)
