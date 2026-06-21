"""Build customization for rime-ecp5.

Project metadata lives in ``pyproject.toml``; this file only adds a build step
that copies the firmware / module / config source trees into ``icepi/_bundled``
so that ``rime build`` works from a pip-installed wheel, where the original
top-level source directories are not shipped as importable data.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

# Source trees bundled into the wheel. Kept in sync with the build system's
# REPO_ROOT-relative layout (firmware/, modules/, config/).
_DATA_DIRS = ("firmware", "modules", "config")
# Build artifacts and caches that must never enter the wheel.
_SKIP_SUFFIXES = {".bit", ".config", ".vcd", ".pyc"}
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".build"}


class _BundleData(build_py):
    """Copy the data trees into ``icepi/_bundled`` before packaging."""

    def run(self) -> None:
        root = Path(__file__).parent.resolve()
        dest_base = root / "icepi" / "_bundled"
        if dest_base.exists():
            shutil.rmtree(dest_base)
        for name in _DATA_DIRS:
            src = root / name
            if not src.is_dir():
                continue
            for f in src.rglob("*"):
                if f.is_dir() or f.suffix in _SKIP_SUFFIXES:
                    continue
                if any(part in _SKIP_DIRS for part in f.parts):
                    continue
                target = dest_base / f.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
        super().run()


setup(cmdclass={"build_py": _BundleData})
