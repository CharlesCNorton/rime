"""FPGA build system: source collection, synthesis, place-and-route, packing."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from icepi.models import ResolvedBitstream
from icepi.tools import BUNDLED_INSTALL, REPO_ROOT, find_oss_cad_tool

__all__ = [
    "BuildError",
    "FIRMWARE_ROOT",
    "IMAGES_ROOT",
    "EXPERIMENTS_ROOT",
    "resolve_project_dir",
    "available_projects",
    "format_known_projects",
    "collect_sources",
    "materialize_lpf",
    "build_project",
    "run_build",
    "resolve_bitstream_target",
]

FIRMWARE_ROOT = REPO_ROOT / "firmware"
CORE_ROOT = FIRMWARE_ROOT / "core"
IMAGES_ROOT = FIRMWARE_ROOT / "images"
EXPERIMENTS_ROOT = REPO_ROOT / "experiments"
MODULES_ROOT = REPO_ROOT / "modules"


class BuildError(RuntimeError):
    """Raised when an FPGA build step fails."""


def _scan_projects(root: Path) -> list[str]:
    """Return project names under *root* that have a top.sv or top.v."""
    if not root.is_dir():
        return []
    return [
        d.name for d in root.iterdir()
        if d.is_dir() and any((d / n).is_file() for n in ("top.sv", "top.v"))
    ]


def available_projects() -> list[str]:
    """Return sorted names of firmware projects, experiments, and modules."""
    return sorted(set(_scan_projects(IMAGES_ROOT) + _scan_projects(EXPERIMENTS_ROOT) + _scan_projects(MODULES_ROOT)))


def resolve_project_dir(name: str) -> Path:
    """Locate a project directory by name, searching images/, experiments/, then modules/."""
    for root in (IMAGES_ROOT, EXPERIMENTS_ROOT, MODULES_ROOT):
        candidate = root / name
        if candidate.is_dir() and (any(candidate.glob("top.sv")) or any(candidate.glob("top.v"))):
            return candidate
    raise BuildError(f"Unknown project: {name}")


def format_known_projects() -> str:
    """Return a comma-separated list of known project names, or ``<none>``."""
    projects = available_projects()
    if not projects:
        return "<none>"
    return ", ".join(projects)


def require_tool(name: str) -> str:
    """Locate an OSS CAD Suite tool or raise :class:`BuildError`."""
    found = find_oss_cad_tool(name, REPO_ROOT)
    if found:
        return found
    raise BuildError(
        f"{name} was not found. Set ICEPI_OSS_CAD_ROOT/ICEPI_OSS_CAD_BIN, keep OSS CAD Suite near the repo, or add it to PATH."
    )


def resolve_lpf(path: Path) -> Path:
    """Follow a single-line symlink-style LPF redirect, or return *path* as-is."""
    text = path.read_text(encoding="utf-8").strip()
    if (
        "\n" not in text
        and text.endswith(".lpf")
        and not text.startswith(("SYSCONFIG", "#", "LOCATE", "BLOCK"))
    ):
        return (path.parent / text).resolve()
    return path


def _strip_comments(text: str) -> str:
    """Remove // and /* */ comments from Verilog/SystemVerilog source text."""
    import re
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text


def collect_sources(project_dir: Path) -> list[Path]:
    """Gather Verilog/SV sources for a project, including shared core modules.

    Starts with all .sv/.v files in the project directory, always includes
    UART RX/TX, then scans the project text for instantiation patterns of
    known core modules (flash_spi_master, sdram_controller, etc.) and
    compositor modules. This auto-detection means a project only pulls in
    the cores it actually instantiates.
    """
    project_sources = sorted(project_dir.glob("*.sv")) + sorted(project_dir.glob("*.v"))
    if not project_sources:
        raise BuildError(f"No Verilog/SystemVerilog sources found in {project_dir}")

    # UART is always included — every image communicates over serial
    sources = list(project_sources)
    sources.extend(
        [
            CORE_ROOT / "uart_rx.sv",
            CORE_ROOT / "uart_tx.sv",
        ]
    )
    # Scan project sources for instantiation patterns to auto-detect dependencies
    project_text = _strip_comments(
        "".join(source.read_text(encoding="utf-8", errors="ignore") for source in project_sources)
    )
    if "flash_spi_master" in project_text:
        sources.append(CORE_ROOT / "flash_spi_master.sv")
    if "sdram_controller" in project_text:
        sources.append(CORE_ROOT / "sdram_controller.sv")
    if "sdram_bridge" in project_text:
        sources.append(CORE_ROOT / "sdram_bridge.sv")
    if "sd_spi_master" in project_text:
        sources.append(CORE_ROOT / "sd_spi_master.sv")
    if "sd_install_engine" in project_text:
        sources.append(CORE_ROOT / "sd_install_engine.sv")
    if "auto_recovery" in project_text:
        sources.append(CORE_ROOT / "auto_recovery.sv")
    if "rime_i_core" in project_text:
        sources.append(MODULES_ROOT / "rime-i" / "rime_i_core.sv")
    if "rime_service" in project_text:
        candidate = IMAGES_ROOT / "rime" / "rime_service.sv"
        if candidate.exists() and candidate.resolve() not in {s.resolve() for s in sources}:
            sources.append(candidate)
    # For each module, search the project text for an instantiation of its
    # top_module (per manifest, falling back to the file stem). The match
    # requires `<top_module> <whitespace> <identifier>` so naked Verilog
    # keywords like `wire` (file stem of modules/wire/wire.sv, but with
    # top_module = "wire_mod") do not produce false positives.
    import json as _json
    import re as _re
    for mod_dir in MODULES_ROOT.iterdir():
        if not mod_dir.is_dir():
            continue
        manifest_path = mod_dir / "module.json"
        top_name: str | None = None
        if manifest_path.exists():
            try:
                top_name = _json.loads(manifest_path.read_text(encoding="utf-8")).get("top_module")
            except Exception:
                top_name = None
        for sv_file in mod_dir.glob("*.sv"):
            if sv_file.stem == "top":
                continue
            search_name = top_name or sv_file.stem
            # Match an instantiation: `<modname> <ident>(` (with optional ws).
            pattern = r'(?<![a-zA-Z0-9_])' + _re.escape(search_name) + r'\s+[A-Za-z_][A-Za-z0-9_]*\s*\('
            if _re.search(pattern, project_text):
                sources.append(sv_file)
    dedup: list[Path] = []
    seen: set[Path] = set()
    for source in sources:
        resolved = source.resolve()
        if resolved not in seen and resolved.exists():
            seen.add(resolved)
            dedup.append(resolved)
    return dedup


def materialize_lpf(project_dir: Path, needs_flash_pins: bool, out_dir: Path | None = None) -> Path:
    """Write a build-time LPF, disabling MASTER_SPI_PORT when flash pins are needed.

    Reads the base constraint from the (possibly read-only) project directory
    and writes the materialized copy to *out_dir* when given, so bundled
    read-only installs can still build into a writable working directory.
    """
    project_lpf = project_dir / "icepi-zero.lpf"
    base_lpf = project_lpf if project_lpf.exists() else FIRMWARE_ROOT / "icepi-zero.lpf"
    resolved = resolve_lpf(base_lpf)
    text = resolved.read_text(encoding="utf-8")
    if needs_flash_pins and "MASTER_SPI_PORT=ENABLE" in text:
        text = text.replace("MASTER_SPI_PORT=ENABLE", "MASTER_SPI_PORT=DISABLE", 1)
    build_lpf = (out_dir or project_dir) / ".build-icepi-zero.lpf"
    build_lpf.write_text(text, encoding="utf-8")
    return build_lpf


def run_external(command: list[str], cwd: Path) -> None:
    """Run a build tool, bootstrapping the OSS CAD Suite environment if available.

    On Windows, sources ``environment.bat`` from the OSS CAD Suite root.
    On Unix, sources ``environment`` (sh) if present, otherwise just adds
    the tool's bin directory to PATH.
    """
    print(" ".join(command))
    env = os.environ.copy()
    tool_path = Path(command[0]).resolve()
    tool_dir = str(tool_path.parent)
    env["PATH"] = tool_dir + os.pathsep + env.get("PATH", "")
    oss_root = tool_path.parent.parent
    if os.name == "nt":
        env_bat = oss_root / "environment.bat"
        if env_bat.exists():
            bootstrap = subprocess.run(
                ["cmd.exe", "/c", f"call {env_bat} && set"],
                cwd=cwd, check=True, capture_output=True, text=True, env=env,
            )
            for line in bootstrap.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    env[key] = value
    else:
        env_sh = oss_root / "environment"
        if env_sh.exists():
            bootstrap = subprocess.run(
                ["bash", "-c", f"source {env_sh} && env"],
                cwd=cwd, check=True, capture_output=True, text=True, env=env,
            )
            for line in bootstrap.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    env[key] = value
    subprocess.run(command, cwd=cwd, check=True, env=env)


def _synth_nosis(
    sources: list[Path],
    json_out: Path,
    *,
    top: str,
    project_dir: Path,
) -> None:
    """Synthesize with nosis, the resident pure-Python ECP5 synthesizer.

    Emits a nextpnr-compatible JSON netlist. Invoked as a subprocess so the
    build does not depend on synthesizer internals.
    """
    include_dirs = sorted({str(source.parent) for source in sources})
    argv = [str(source) for source in sources]
    argv += ["--top", top, "-o", json_out.name]
    for directory in include_dirs:
        argv += ["-I", directory]
    run_external([sys.executable, "-m", "nosis", *argv], cwd=project_dir)


def build_project(
    project: str,
    *,
    clean: bool = False,
    top: str = "top",
    package: str = "CABGA256",
    fpga_size: str = "25k",
) -> Path:
    """Run the full synthesis -> nextpnr -> ecppack pipeline and return the bitstream path."""
    project_dir = resolve_project_dir(project)

    # In a source checkout, build in place beside the project. When installed
    # as a wheel the sources are read-only bundled data, so write every
    # artifact to a writable working directory under the caller's cwd.
    out_dir = project_dir
    if BUNDLED_INSTALL:
        out_dir = Path.cwd() / "rime-build" / project
        out_dir.mkdir(parents=True, exist_ok=True)

    bitstream = out_dir / "bitstream.bit"
    json_out = out_dir / "bitstream.json"
    config_out = out_dir / "bitstream.config"
    # Always clean build artifacts. Stale bitstreams from prior synthesis
    # runs cause silent failures that are indistinguishable from HDL bugs.
    for path in (bitstream, json_out, config_out, out_dir / ".build-icepi-zero.lpf"):
        path.unlink(missing_ok=True)

    sources = collect_sources(project_dir)

    needs_flash_service = any(source.name == "flash_service.sv" for source in sources)
    needs_usrmclk = needs_flash_service or any(
        "USRMCLK" in source.read_text(encoding="utf-8", errors="ignore")
        for source in sources
        if source.name.endswith((".sv", ".v"))
    )
    build_lpf = materialize_lpf(project_dir, needs_usrmclk, out_dir=out_dir)

    build_config = project_dir / "build.json"
    extra_nextpnr: list[str] = []
    if build_config.is_file():
        import json as _json
        cfg = _json.loads(build_config.read_text(encoding="utf-8"))
        extra_nextpnr = cfg.get("nextpnr_flags", [])

    _synth_nosis(sources, json_out, top=top, project_dir=out_dir)

    nextpnr = require_tool("nextpnr-ecp5")
    ecppack = require_tool("ecppack")

    run_external(
        [
            nextpnr,
            f"--{fpga_size}",
            "--package",
            package,
            "--seed",
            "1",
            "--lpf",
            build_lpf.name,
            "--json",
            json_out.name,
            "--textcfg",
            config_out.name,
            *extra_nextpnr,
        ],
        cwd=out_dir,
    )
    run_external([ecppack, "--compress", config_out.name, bitstream.name], cwd=out_dir)
    return bitstream.resolve()


def run_build(
    project: str,
    *,
    clean: bool = False,
    top: str = "top",
    package: str = "CABGA256",
    fpga_size: str = "25k",
) -> Path:
    """Validate the project name, build, and return the bitstream path."""
    if project not in available_projects():
        raise ValueError(f"unknown project `{project}` (known: {format_known_projects()})")
    bitstream = build_project(
        project, clean=clean, top=top, package=package, fpga_size=fpga_size,
    )
    if not bitstream.exists():
        raise FileNotFoundError(bitstream)
    return bitstream


def patch_bram(
    project: str,
    *,
    package: str = "CABGA256",
    fpga_size: str = "25k",
) -> Path:
    """Patch BRAM contents in an existing bitstream using ecpbram.

    Recompiles the C firmware (``make`` in the ``fw/`` subdirectory),
    then uses ``ecpbram`` to swap the old firmware.hex with the new one
    inside the existing bitstream.config. Finally re-runs ``ecppack``.
    No synthesis or place-and-route is needed.
    """
    project_dir = resolve_project_dir(project)
    config_out = project_dir / "bitstream.config"
    bitstream = project_dir / "bitstream.bit"
    if not config_out.exists():
        raise BuildError("No bitstream.config found — run a full build first")
    fw_dir = project_dir / "fw"
    if not fw_dir.is_dir():
        raise BuildError(f"No fw/ directory in {project} — ecpbram patch requires C firmware")
    fw_hex = project_dir / "firmware.hex"
    if not fw_hex.exists():
        raise BuildError("No firmware.hex found — run a full build first")
    old_hex = project_dir / "firmware_old.hex"
    old_hex.write_text(fw_hex.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["make", "-C", str(fw_dir), "clean"], check=True)
    subprocess.run(["make", "-C", str(fw_dir)], check=True)
    boot_dir = project_dir / "boot"
    boot_hex = project_dir / "boot_rom.hex"
    if boot_dir.is_dir() and boot_hex.exists():
        old_boot_hex = project_dir / "boot_rom_old.hex"
        old_boot_hex.write_text(boot_hex.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run(["make", "-C", str(boot_dir), "clean"], check=True)
        subprocess.run(["make", "-C", str(boot_dir)], check=True)
    ecpbram = require_tool("ecpbram")
    ecppack = require_tool("ecppack")
    patched_config = project_dir / "bitstream_patched.config"
    run_external(
        [ecpbram, "-i", config_out.name, "-o", patched_config.name,
         "-f", old_hex.name, "-t", fw_hex.name],
        cwd=project_dir,
    )
    if boot_dir.is_dir() and (project_dir / "boot_rom_old.hex").exists():
        patched2 = project_dir / "bitstream_patched2.config"
        run_external(
            [ecpbram, "-i", patched_config.name, "-o", patched2.name,
             "-f", "boot_rom_old.hex", "-t", "boot_rom.hex"],
            cwd=project_dir,
        )
        patched2.rename(patched_config)
    patched_config.rename(config_out)
    run_external([ecppack, "--compress", config_out.name, bitstream.name], cwd=project_dir)
    old_hex.unlink(missing_ok=True)
    (project_dir / "boot_rom_old.hex").unlink(missing_ok=True)
    print(f"Patched {bitstream}")
    return bitstream.resolve()


def resolve_bitstream_target(
    spec: str,
    *,
    build_if_project: bool = False,
    clean: bool = False,
) -> ResolvedBitstream:
    """Resolve a CLI spec (project name, directory, or .bit path) to a bitstream."""
    raw = Path(spec).expanduser()
    if raw.name.endswith(".bundle.bin"):
        raise ValueError(
            "bundle files are SD install artifacts; copy them onto media and use `sd-install <lba>`, or use the underlying .bit/project for direct host install"
        )

    if raw.exists():
        resolved = raw.resolve()
        if resolved.is_file():
            return ResolvedBitstream(spec=spec, bitstream=resolved, project=None, built=False)
        if resolved.is_dir():
            project = resolved.name
            bitstream = resolved / "bitstream.bit"
            if any(resolved.glob("*.sv")):
                if build_if_project:
                    built = run_build(project, clean=clean)
                    return ResolvedBitstream(spec=spec, bitstream=built, project=project, built=True)
                if not bitstream.exists():
                    raise FileNotFoundError(
                        f"project `{project}` has no bitstream yet; run `build {project}` or pass `--build`"
                    )
                return ResolvedBitstream(
                    spec=spec,
                    bitstream=bitstream.resolve(),
                    project=project,
                    built=False,
                )
            raise ValueError(f"`{resolved}` is a directory but not a firmware project")

    try:
        project_dir = resolve_project_dir(spec)
    except BuildError:
        project_dir = None
    if project_dir is not None and project_dir.is_dir():
        project = project_dir.name
        bitstream = project_dir / "bitstream.bit"
        if build_if_project:
            built = run_build(project, clean=clean)
            return ResolvedBitstream(spec=spec, bitstream=built, project=project, built=True)
        if not bitstream.exists():
            raise FileNotFoundError(
                f"project `{project}` has no bitstream yet; run `build {project}` or pass `--build`"
            )
        return ResolvedBitstream(
            spec=spec,
            bitstream=bitstream.resolve(),
            project=project,
            built=False,
        )

    raise FileNotFoundError(
        f"`{spec}` was not found as a file or project (known projects: {format_known_projects()})"
    )
