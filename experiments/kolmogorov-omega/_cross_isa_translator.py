#!/usr/bin/env python3
"""Cross-ISA program translation.

Given a program P that produces output X under ISA-A, find the shortest
program Q that produces the same X under ISA-B. Decode both programs
to human-readable opcode sequences. The tensor is the cross-reference table."""
import numpy as np
import json

OP_NAMES = {0:'INC',1:'DEC',2:'SWP',3:'ADD',4:'XOR',6:'NEG',7:'MOV',
            8:'SUB',9:'AND',10:'OR',11:'SHR',12:'SHL',13:'CPL',14:'NOP'}

data = np.load("experiments/kolmogorov-omega/output_tensor.npz")
hist = data["hist"]
k_prog = data["k_prog"]
halting = data["halting"]
ops_arr = data["ops"]

N = 8

def decode_program(prog_idx):
    digits = []
    tmp = prog_idx
    for _ in range(N):
        digits.append(tmp % 6)
        tmp //= 6
    return digits

def program_to_str(digits, isa_ops):
    names = []
    for d in digits:
        if d == 5:
            names.append("JNZ")
        else:
            names.append(OP_NAMES.get(isa_ops[d], f"?{d}"))
    return " ".join(names)

def find_isa_index(o1, o2, o3, o4):
    for i in range(len(ops_arr)):
        if ops_arr[i,0]==o1 and ops_arr[i,1]==o2 and ops_arr[i,2]==o3 and ops_arr[i,3]==o4:
            return i
    return -1

def isa_ops_list(idx):
    o = ops_arr[idx]
    return [0, int(o[0]), int(o[1]), int(o[2]), int(o[3])]

ISAS = {
    "A": (1,2,3,4),
    "B": (6,7,8,9),
    "C": (11,13,3,10),
    "E": (6,2,13,4),
    "G": (11,7,8,9),
    "MIN": (0,0,0,0),
    "MAX": (9,9,9,9),
}

def main():
    print("=== CROSS-ISA PROGRAM TRANSLATOR ===\n")

    isa_indices = {}
    for name, key in ISAS.items():
        idx = find_isa_index(*key)
        if idx >= 0:
            isa_indices[name] = idx

    print("Translation table: for each output x reachable under source ISA,")
    print("find the shortest program under target ISA that produces the same x.\n")

    results = []

    pairs = [("A","B"), ("A","G"), ("B","A"), ("G","A"), ("A","MAX"), ("MAX","A"), ("MIN","A")]

    for src_name, tgt_name in pairs:
        src_idx = isa_indices.get(src_name)
        tgt_idx = isa_indices.get(tgt_name)
        if src_idx is None or tgt_idx is None:
            continue

        src_ops = isa_ops_list(src_idx)
        tgt_ops = isa_ops_list(tgt_idx)

        src_kp = k_prog[src_idx]
        tgt_kp = k_prog[tgt_idx]

        translatable = 0
        untranslatable = 0
        translations = []

        for x in range(256):
            if src_kp[x] < 0:
                continue
            src_prog = decode_program(int(src_kp[x]))
            src_str = program_to_str(src_prog, src_ops)

            if tgt_kp[x] >= 0:
                tgt_prog = decode_program(int(tgt_kp[x]))
                tgt_str = program_to_str(tgt_prog, tgt_ops)
                translatable += 1
                translations.append({
                    "output": x,
                    "src_prog_idx": int(src_kp[x]),
                    "src_prog": src_str,
                    "tgt_prog_idx": int(tgt_kp[x]),
                    "tgt_prog": tgt_str,
                })
            else:
                untranslatable += 1
                translations.append({
                    "output": x,
                    "src_prog_idx": int(src_kp[x]),
                    "src_prog": src_str,
                    "tgt_prog_idx": -1,
                    "tgt_prog": "UNREACHABLE",
                })

        src_reach = int(np.sum(src_kp >= 0))
        tgt_reach = int(np.sum(tgt_kp >= 0))

        print(f"--- {src_name} -> {tgt_name} ---")
        print(f"Source reachable: {src_reach}  Target reachable: {tgt_reach}")
        print(f"Translatable: {translatable}  Untranslatable: {untranslatable}")
        if translatable > 0:
            print(f"Translation coverage: {translatable}/{src_reach} ({translatable*100//src_reach}%)")

        print(f"\nSample translations (first 10):")
        shown = 0
        for t in translations:
            if t["tgt_prog"] == "UNREACHABLE":
                continue
            if shown >= 10:
                break
            print(f"  x={t['output']:3d}: [{t['src_prog']}] -> [{t['tgt_prog']}]")
            shown += 1

        if untranslatable > 0:
            print(f"\nUntranslatable outputs (first 10):")
            shown = 0
            for t in translations:
                if t["tgt_prog"] != "UNREACHABLE":
                    continue
                if shown >= 10:
                    break
                print(f"  x={t['output']:3d}: [{t['src_prog']}] -> UNREACHABLE")
                shown += 1

        print()
        results.append({
            "source": src_name, "target": tgt_name,
            "src_reachable": src_reach, "tgt_reachable": tgt_reach,
            "translatable": translatable, "untranslatable": untranslatable,
            "sample": translations[:20],
        })

    print("=== TRANSLATION ASYMMETRY ===")
    for r in results:
        total = r["translatable"] + r["untranslatable"]
        pct = r["translatable"] * 100 // total if total > 0 else 0
        print(f"  {r['source']:>3s} -> {r['target']:<3s}: {r['translatable']:>4d}/{total} ({pct}%)")

    with open("experiments/kolmogorov-omega/cross_isa_translations.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote cross_isa_translations.json")

if __name__ == "__main__":
    main()
