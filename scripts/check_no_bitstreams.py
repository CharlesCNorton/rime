"""Pre-commit hook: reject any tracked .bit/.config artifacts at the repo root.

The build system emits these into project directories by design. Having them
at the repo root is always accidental and should never land in a commit.
"""
from __future__ import annotations

import sys
from pathlib import Path

BAD_EXTENSIONS = {".bit", ".config"}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    offenders = [
        p for p in root.iterdir()
        if p.is_file() and p.suffix in BAD_EXTENSIONS
    ]
    if offenders:
        print("error: tracked bitstream artifacts at repo root:", file=sys.stderr)
        for p in offenders:
            print(f"  {p.name}", file=sys.stderr)
        print("Move them under their project directory or delete them.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
