#!/usr/bin/env python3
"""Build self-referential experiment with ecpbram firmware patching.

1. Synthesize with LFSR seed pattern in BRAM
2. ecpbram: replace seed with real firmware
3. ecppack: produce final bitstream
4. Optionally flash via JTAG

This treats BRAM content as a post-synthesis operation, sidestepping
INITVAL propagation through synthesis entirely.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from icepi.build import build_project  # noqa: E402
from icepi.tools import find_oss_cad_tool  # noqa: E402


def get_env():
    """Bootstrap OSS CAD Suite environment."""
    tool = find_oss_cad_tool("ecpbram", REPO)
    env = os.environ.copy()
    oss_root = Path(tool).parent.parent
    env_bat = oss_root / "environment.bat"
    if os.name == "nt" and env_bat.exists():
        r = subprocess.run(
            ["cmd.exe", "/c", str(env_bat), "&&", "set"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        for line in r.stdout.splitlines():
            if "=" in line and not line.startswith(" "):
                k, _, v = line.partition("=")
                env[k] = v
    return env


def main():
    exp = Path(__file__).resolve().parent
    seed_hex = exp / "bram_seed.hex"
    firmware_hex = exp / "firmware_real.hex"
    config_in = exp / "bitstream.config"
    config_out = exp / "bitstream_patched.config"
    bitstream_out = exp / "bitstream_patched.bit"

    if not seed_hex.exists():
        print(f"Missing {seed_hex}")
        return 1
    if not firmware_hex.exists():
        print(f"Missing {firmware_hex}")
        return 1

    # Step 1: Synthesize with seed pattern
    print("=== Step 1: Synthesis ===")
    build_project("self-referential", clean=True)

    if not config_in.exists():
        print(f"Synthesis failed — no {config_in}")
        return 1

    # Step 2: ecpbram patch
    print("\n=== Step 2: ecpbram ===")
    env = get_env()
    ecpbram = find_oss_cad_tool("ecpbram", REPO)
    r = subprocess.run(
        [ecpbram, "-i", str(config_in), "-o", str(config_out),
         "-f", str(seed_hex), "-t", str(firmware_hex)],
        capture_output=True, text=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        print(f"ecpbram failed: {r.stderr.strip()}")
        return 1
    print(f"Patched: {config_out.name}")

    # Step 3: ecppack
    print("\n=== Step 3: ecppack ===")
    ecppack = find_oss_cad_tool("ecppack", REPO)
    r = subprocess.run(
        [ecppack, "--compress", str(config_out), str(bitstream_out)],
        capture_output=True, text=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        print(f"ecppack failed: {r.stderr.strip()}")
        return 1
    print(f"Bitstream: {bitstream_out.name} ({bitstream_out.stat().st_size} bytes)")

    # Step 4: Flash if requested
    if "--flash" in sys.argv:
        print("\n=== Step 4: Flash ===")
        loader = find_oss_cad_tool("openFPGALoader", REPO)
        # Switch to JTAG
        subprocess.run([sys.executable, str(REPO / "icepi_admin.py"), "jtag"],
                       capture_output=True, timeout=30)
        # Load SRAM
        r = subprocess.run(
            [loader, "-b", "icepi-zero", str(bitstream_out)],
            capture_output=True, text=True, env=env, timeout=60,
        )
        if r.returncode != 0:
            print(f"Flash failed: {r.stderr.strip()}")
            return 1
        print("SRAM loaded")
        # Switch to UART
        subprocess.run([sys.executable, str(REPO / "icepi_admin.py"), "uart"],
                       capture_output=True, timeout=30)
        print("Ready on UART")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
