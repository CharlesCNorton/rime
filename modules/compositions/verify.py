#!/usr/bin/env python3
"""Host verifier for themed composition silicon regressions.

Reads the labelled silicon output (NAME:HEX lines) and compares each
value against the composition's Python predictor.

Usage:
    python modules/compositions/verify.py <image>

Where <image> is one of: gauntlet, seal, servo, ingest, profile, evolve.

Assumes the bitstream is already built and flashed; uses the
compositor_test.flash_and_read helper to load and read.
"""
import sys
import importlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "modules"))
sys.path.insert(0, str(REPO / "modules" / "compositions"))


def parse_silicon(text, done_marker):
    """Find the most recent complete iteration in the buffer.

    The firmware loops continuously, so the captured buffer may start
    mid-iteration. Walk back from the last DONE marker to either the
    previous DONE marker or buffer start.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    done_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith(done_marker):
            done_idx = i
            break
    if done_idx < 0:
        return {}
    start_idx = 0
    for i in range(done_idx - 1, -1, -1):
        if lines[i].startswith(done_marker):
            start_idx = i + 1
            break
    silicon = {}
    for line in lines[start_idx:done_idx]:
        if ":" in line:
            k, _, v = line.partition(":")
            try:
                silicon[k] = int(v, 16)
            except ValueError:
                pass
    return silicon


def verify_image(image_name):
    images = {
        "gauntlet": ("gauntlet", "GAUNTLET", "compute", "COMPUTE_MODULES", "generate_firmware", "predict"),
        "seal":     ("seal",     "SEAL",     "crypto",  "CRYPTO_MODULES",  "generate_firmware", "predict"),
        "servo":    ("servo",    "SERVO",    "control", "CONTROL_MODULES", "generate_firmware", "predict"),
        "ingest":   ("ingest",   "INGEST",   "data",    "DATA_MODULES",    "generate_firmware", "predict"),
        "profile":  ("profile",  "PROFILE",  "observe", "OBS_MODULES",     "generate_firmware", "predict"),
        "evolve":   ("evolve",   "EVOLVE",   "sim",     "SIM_MODULES",     "generate_firmware", "predict"),
    }
    if image_name not in images:
        print(f"unknown image: {image_name}")
        print(f"valid: {', '.join(images)}")
        return 1

    mod_name, done_marker, theme, modules_attr, gen_attr, predict_attr = images[image_name]
    mod = importlib.import_module(mod_name)
    modules = getattr(mod, modules_attr)
    generate_firmware = getattr(mod, gen_attr)
    predict = getattr(mod, predict_attr)

    print(f"=== {image_name} silicon verification ===")
    print(f"Composition: {len(modules)} modules ({theme})")

    from icepi.compose import generate_and_build
    firmware = generate_firmware()
    # generate_and_build writes top.sv AND firmware.hex (the BRAM $readmemh image)
    # before synthesis; emitting only top.sv would abort synthesis on the missing hex.
    _, bitstream = generate_and_build(modules, firmware, clean=True)
    print(f"Built {bitstream}")

    from compositor_test import flash_and_read, restore_rime
    output = flash_and_read("compositions")
    restore_rime()

    silicon = parse_silicon(output, done_marker)
    expected = predict()

    matches = checked = 0
    for label in expected:
        s = silicon.get(label)
        e = expected[label]
        if s is None:
            print(f"  {label:10s}: MISSING")
            continue
        if e is None:
            print(f"  {label:10s}: 0x{s:08X} (variable)")
        else:
            checked += 1
            tag = "PASS" if s == e else "FAIL"
            if s == e:
                matches += 1
                print(f"  {label:10s}: 0x{s:08X} {tag}")
            else:
                print(f"  {label:10s}: silicon=0x{s:08X} expected=0x{e:08X} {tag}")

    print(f"\n{image_name.upper()}: {matches}/{checked} verified, {len(silicon)} total readbacks")
    return 0 if matches == checked else 1


def main():
    if len(sys.argv) < 2:
        print("usage: python modules/compositions/verify.py <image>")
        return 1
    return verify_image(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
