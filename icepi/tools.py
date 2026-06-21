"""Shared path resolution, tool discovery, and small utility functions."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from time import monotonic
from typing import Callable

__all__ = [
    "REPO_ROOT",
    "ProgressCallback",
    "parse_int_value",
    "candidate_oss_cad_bin_dirs",
    "find_oss_cad_tool",
    "current_python_command",
    "pip_install_hint",
    "admin_script_command",
    "render_command",
    "find_admin_script",
    "uart_restore_hint",
    "make_progress_renderer",
    "strip_bitstream_header",
]

def _find_repo_root() -> Path:
    """Locate the RIME repository root.

    Walks upward from this file looking for ``config/icepi-layout.json``
    as the anchor.  Falls back to the parent of the ``icepi/`` package
    directory when running from a source checkout.
    """
    candidate = Path(__file__).resolve().parent.parent
    for _ in range(4):
        if (candidate / "config" / "icepi-layout.json").is_file():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    # Installed wheel: the firmware/modules/config trees are bundled under the
    # package as icepi/_bundled/ (see setup.py). Anchor there when the source
    # checkout layout is absent.
    bundled = Path(__file__).resolve().parent / "_bundled"
    if (bundled / "config" / "icepi-layout.json").is_file():
        return bundled
    return Path(__file__).resolve().parent.parent


REPO_ROOT = _find_repo_root()
# True when running from a pip-installed wheel (sources are read-only bundled
# data); build outputs are then redirected to a writable working directory.
BUNDLED_INSTALL = REPO_ROOT.name == "_bundled"

ProgressCallback = Callable[[str, int, int, str | None], None]


def _parse_int(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = value.strip()
    return int(text, 0)


def strip_bitstream_header(data: bytes) -> bytes:
    """Return the ECP5 config from an ecppack ``.bit`` for direct SPI-flash boot.

    ecppack prepends an ASCII comment header before the config preamble; the
    config begins at the run of 0xFF padding before the first 0xBDB3 sync word.
    The ECP5 reads SPI flash from address 0, so the header is removed before
    flashing. Returns *data* unchanged when no sync word is present; idempotent.
    """
    sync = data.find(b"\xbd\xb3")
    if sync < 0:
        return data
    start = sync
    while start > 0 and data[start - 1] == 0xFF:
        start -= 1
    return data[start:]


def parse_int_value(value: str) -> int:
    """Parse an integer from a CLI string (supports ``0x`` hex prefix)."""
    return int(value, 0)


def _align_up(value: int, alignment: int) -> int:
    if alignment <= 0:
        raise ValueError("alignment must be positive")
    return ((value + alignment - 1) // alignment) * alignment


def _ascii_slot_name(value: str) -> bytes:
    encoded = value.encode("ascii", errors="ignore")[:32]
    return encoded.ljust(32, b"\x00")



def _dedupe_paths(paths: list[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _split_env_paths(value: str | None) -> list[Path]:
    if not value:
        return []
    return [Path(part) for part in value.split(os.pathsep) if part.strip()]



def candidate_oss_cad_bin_dirs(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return candidate bin directories for OSS CAD Suite tools."""
    candidates: list[Path] = []

    for env_name in ("ICEPI_OSS_CAD_BIN", "OSS_CAD_BIN"):
        candidates.extend(_split_env_paths(os.environ.get(env_name)))

    for env_name in ("ICEPI_OSS_CAD_ROOT", "OSS_CAD_ROOT", "OSS_CAD_SUITE"):
        for base in _split_env_paths(os.environ.get(env_name)):
            candidates.append(base / "bin")
            candidates.append(base / "oss-cad-suite" / "bin")

    anchors = [repo_root, repo_root.parent, Path.cwd(), Path.cwd().parent]
    candidates.extend([anchor / "oss-cad-suite" / "bin" for anchor in anchors])
    candidates.extend([anchor / "oss-cad-suite" / "oss-cad-suite" / "bin" for anchor in anchors])

    return [path for path in _dedupe_paths(candidates) if path.is_dir()]


def find_oss_cad_tool(name: str, repo_root: Path = REPO_ROOT) -> str | None:
    """Locate an OSS CAD Suite binary by name, or return *None*."""
    names = [f"{name}.exe", name] if os.name == "nt" else [name]
    for bin_dir in candidate_oss_cad_bin_dirs(repo_root):
        for tool_name in names:
            candidate = bin_dir / tool_name
            if candidate.exists():
                return str(candidate)
    for tool_name in names:
        found = shutil.which(tool_name)
        if found:
            return found
    return None



def current_python_command() -> str:
    """Return the current Python interpreter as a shell-safe command string."""
    executable = sys.executable or "python"
    return subprocess.list2cmdline([executable])


def pip_install_hint(package: str) -> str:
    """Return a shell command string to pip-install *package*."""
    return f"{current_python_command()} -m pip install {package}"


def admin_script_command(script: Path, *args: str) -> list[str]:
    """Build a command list to invoke an admin script (prefixes Python for .py files)."""
    if script.suffix.lower() == ".py":
        executable = os.environ.get("ICEPI_PYTHON") or (sys.executable or "python")
        return [executable, str(script), *args]
    return [str(script), *args]


def render_command(parts: list[str]) -> str:
    """Format a command list as a platform-appropriate shell string."""
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def find_admin_script() -> Path | None:
    """Locate the repo-local administrative wrapper script."""
    env_override = os.environ.get("ICEPI_ADMIN_SCRIPT")
    if env_override:
        candidate = Path(env_override).expanduser()
        if candidate.exists():
            return candidate

    candidates = _dedupe_paths(
        [
            REPO_ROOT / "icepi_admin.py",
            REPO_ROOT / "scripts" / "icepi_admin.py",
            Path.cwd() / "icepi_admin.py",
            Path.cwd() / "scripts" / "icepi_admin.py",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def uart_restore_hint() -> str:
    """Return a human-readable hint for restoring UART mode."""
    script = find_admin_script()
    if script is not None:
        command = render_command(admin_script_command(script, "uart"))
        return f"Hint: run `{command}` to restore UART mode."
    return "Hint: restore the serial interface or use your local admin wrapper to return the board to UART mode."



def make_progress_renderer(verbose: bool) -> ProgressCallback:
    """Return a callback that prints stage/done/total progress lines."""
    state = {"last_emit": 0.0}

    def emit(stage: str, done: int, total: int, detail: str | None) -> None:
        now = monotonic()
        if done != total and (now - state["last_emit"]) < 0.25:
            return
        state["last_emit"] = now
        if total <= 0:
            total = 1
        percent = 100.0 * done / total
        suffix = f" {detail}" if detail else ""
        if verbose or done == total:
            print(f"{stage:>6} {done:4d}/{total:<4d} {percent:6.1f}%{suffix}")

    return emit
