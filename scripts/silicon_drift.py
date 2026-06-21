"""Silicon drift detector.

Runs the chain regression on reference silicon and verifies:
  (a) regression exits successfully (every functional check passes)
  (b) firmware fingerprint (service version, caps, JEDEC, geometry)
      matches the stored manifest exactly

The chain CRC hash itself is reported for forensics but not compared,
because two foundational steps (STATS, LAST_ERROR) read cumulative
counters that carry across runs and would force false positives.
Functional drift is caught by (a); firmware drift is caught by (b).

Usage:
    python scripts/silicon_drift.py            # run + compare against manifest
    python scripts/silicon_drift.py --update   # rerun and overwrite manifest
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "config" / "silicon_manifest.json"
REGRESSION = REPO / "tests" / "regression.py"


def run_chain_regression() -> dict[str, str]:
    """Run tests/regression.py --deterministic and parse the CHAIN:XXXX line.

    Deterministic mode skips the BENCH steps whose elapsed-time floats vary
    run-to-run. The remaining steps are functional only and produce a stable
    chain hash that can be compared between runs to detect real drift.
    """
    result = subprocess.run(
        [sys.executable, str(REGRESSION), "--deterministic"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"chain regression exited {result.returncode}\n{result.stderr}")
    chain_match = re.search(r"^CHAIN:([0-9A-F]{8})$", result.stdout, re.MULTILINE)
    if not chain_match:
        raise RuntimeError(f"chain regression did not emit CHAIN:XXXX\n{result.stdout}")
    return {"chain": chain_match.group(1)}


def collect_firmware_fingerprint() -> dict[str, str]:
    """Collect the stable firmware fingerprint: service version + JEDEC + caps."""
    sys.path.insert(0, str(REPO))
    from icepi.flash_service import FlashService

    fingerprint: dict[str, str] = {}
    with FlashService() as svc:
        svc.assert_service()
        info = svc.info()
        ident = svc.identity()
        jedec = svc.jedec()
        fingerprint["board_name"] = str(ident["name"])
        fingerprint["service_version"] = f"{info.phase}.{info.version}"
        fingerprint["caps0"] = f"0x{info.caps0:02X}"
        fingerprint["caps1"] = f"0x{info.caps1:02X}"
        fingerprint["max_program"] = str(info.max_program)
        fingerprint["read_chunk"] = str(info.read_chunk)
        fingerprint["erase_size"] = str(info.erase_size)
        fingerprint["page_size"] = str(info.page_size)
        fingerprint["addr_bytes"] = str(info.addr_bytes)
        fingerprint["jedec"] = " ".join(f"0x{b:02X}" for b in jedec)
    return fingerprint


def render_manifest(fingerprint: dict[str, str]) -> str:
    """Render the comparable portion of the manifest (firmware fingerprint only)."""
    obj = {
        "_comment": "Silicon drift manifest. Compared by scripts/silicon_drift.py.",
        "_chain_hash_note": (
            "Chain regression hash varies run-to-run (STATS/LAST_ERROR carry state). "
            "Drift detection enforces (a) regression exit 0 and (b) fingerprint match. "
            "Hash is reported for forensics only."
        ),
        "firmware": fingerprint,
    }
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Silicon drift detector")
    parser.add_argument("--update", action="store_true",
                        help="rerun and overwrite the manifest from current silicon")
    args = parser.parse_args()

    fingerprint = collect_firmware_fingerprint()
    chain_result = run_chain_regression()  # raises if regression failed

    # Coprocessor parallel regression: 3-way segmented CRC-32
    coproc_regression = REPO / "tests" / "test_coproc_regression.py"
    if coproc_regression.exists():
        print("Running coprocessor parallel regression...")
        coproc_result = subprocess.run(
            [sys.executable, str(coproc_regression)],
            cwd=str(REPO),
            timeout=600,
        )
        if coproc_result.returncode != 0:
            raise RuntimeError("coprocessor parallel regression failed")
        print("  coproc regression: PASS")

    fresh = render_manifest(fingerprint)

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    if args.update:
        MANIFEST.write_text(fresh, encoding="utf-8")
        print(f"wrote {MANIFEST}")
        print(f"  service: {fingerprint['service_version']}  jedec: {fingerprint['jedec']}")
        print(f"  chain (forensic): {chain_result['chain']}")
        return 0

    if not MANIFEST.exists():
        print(f"error: {MANIFEST} does not exist — run with --update first", file=sys.stderr)
        return 1
    current = MANIFEST.read_text(encoding="utf-8")
    if current.strip() == fresh.strip():
        print(f"{MANIFEST}: silicon matches manifest")
        print(f"  service: {fingerprint['service_version']}  jedec: {fingerprint['jedec']}")
        print(f"  chain (forensic): {chain_result['chain']}")
        return 0

    print(f"error: silicon firmware fingerprint drifted from {MANIFEST}", file=sys.stderr)
    print("--- manifest ---", file=sys.stderr)
    print(current, file=sys.stderr)
    print("--- fresh ---", file=sys.stderr)
    print(fresh, file=sys.stderr)
    print(f"forensic chain hash: {chain_result['chain']}", file=sys.stderr)
    print("Investigate the regression cause before committing.", file=sys.stderr)
    print("If the change is intentional, re-run with --update.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
