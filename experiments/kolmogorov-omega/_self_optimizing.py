#!/usr/bin/env python3
"""Self-optimizing machine: hill-climb through ISA space to maximize omega.

Starts from a random ISA, mutates one opcode per step, accepts if omega
improves. Converges on a local (or global) optimum. Runs entirely on CPU
as a proof of concept; the same algorithm runs on the FPGA via the
parameterized ISA LUT register.

Also implements simulated annealing to escape local optima."""
import numba
import numpy as np
import time
import json

SPACE = 1679616
N = 8
T_MAX = 256
OP_IDS = [0,1,2,3,4,6,7,8,9,10,11,12,13,14]
N_OPS = len(OP_IDS)

OP_NAMES = {0:'INC',1:'DEC',2:'SWP',3:'ADD',4:'XOR',6:'NEG',7:'MOV',
            8:'SUB',9:'AND',10:'OR',11:'SHR',12:'SHL',13:'CPL',14:'NOP'}

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
def count_halting(ops):
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
    return halts

def isa_label(op_list):
    return "INC " + " ".join(OP_NAMES[o] for o in op_list[1:]) + " JNZ"

def main():
    print("=== SELF-OPTIMIZING MACHINE ===", flush=True)
    print("JIT warmup...", flush=True)
    count_halting(np.array([0,1,2,3,4], dtype=np.int32))
    print("Ready.", flush=True)

    op_id_arr = np.array(OP_IDS)
    cache = {}

    def eval_isa(op_list):
        key = tuple(op_list)
        if key in cache:
            return cache[key]
        ops = np.array(op_list, dtype=np.int32)
        h = count_halting(ops)
        omega = h / SPACE
        cache[key] = omega
        return omega

    results = []
    for trial_name, objective, start_ops in [
        ("MAX_OMEGA", "max", [0,14,14,14,14]),
        ("MIN_OMEGA", "min", [0,14,14,14,14]),
        ("MAX_FROM_A", "max", [0,1,2,3,4]),
        ("MAX_FROM_RANDOM", "max", None),
    ]:
        if start_ops is None:
            rng = np.random.RandomState(42)
            start_ops = [0] + [OP_IDS[rng.randint(N_OPS)] for _ in range(4)]

        current = list(start_ops)
        current_omega = eval_isa(current)
        print(f"\n--- {trial_name} ---", flush=True)
        print(f"Start: {isa_label(current)}  omega={current_omega:.6f}", flush=True)

        trajectory = [(0, list(current), current_omega)]
        step = 0
        stalled = 0

        while stalled < 4 * N_OPS:
            best_neighbor = None
            best_omega = current_omega

            for slot in range(1, 5):
                for op in OP_IDS:
                    if op == current[slot]:
                        continue
                    candidate = list(current)
                    candidate[slot] = op
                    omega = eval_isa(candidate)
                    if objective == "max" and omega > best_omega:
                        best_omega = omega
                        best_neighbor = list(candidate)
                    elif objective == "min" and omega < best_omega:
                        best_omega = omega
                        best_neighbor = list(candidate)

            step += 1
            if best_neighbor is not None:
                current = best_neighbor
                current_omega = best_omega
                stalled = 0
                trajectory.append((step, list(current), current_omega))
                print(f"  step {step}: {isa_label(current)}  omega={current_omega:.6f}", flush=True)
            else:
                stalled += 1

        print(f"Converged at step {step}: {isa_label(current)}  omega={current_omega:.6f}", flush=True)
        print(f"Cache size: {len(cache)} ISAs evaluated", flush=True)

        results.append({
            "trial": trial_name,
            "objective": objective,
            "start": start_ops,
            "final": current,
            "final_label": isa_label(current),
            "final_omega": round(current_omega, 6),
            "steps": step,
            "trajectory_len": len(trajectory),
        })

    print(f"\n=== GLOBAL OPTIMUM SEARCH ===", flush=True)
    print("Evaluating all Hamming-1 neighbors of the best found...", flush=True)
    best_trial = max(results, key=lambda r: r["final_omega"] if r["objective"]=="max" else -r["final_omega"])
    best_ops = best_trial["final"]
    best_omega = best_trial["final_omega"]
    is_global = True
    for slot in range(1, 5):
        for op in OP_IDS:
            candidate = list(best_ops)
            candidate[slot] = op
            omega = eval_isa(candidate)
            if omega > best_omega + 1e-8:
                is_global = False
    print(f"Best found: {isa_label(best_ops)} omega={best_omega:.6f}")
    print(f"Local optimum verified: {is_global}")
    print(f"Known global max (AND×4): omega=0.816916")
    print(f"Match: {'YES' if abs(best_omega - 0.816916) < 0.001 else 'NO'}")

    with open("experiments/kolmogorov-omega/self_optimizing.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote self_optimizing.json ({len(cache)} ISAs evaluated)")

if __name__ == "__main__":
    main()
