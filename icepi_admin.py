"""icepi_admin: administrative wrapper for IcePi Zero board management.

Handles USB driver switching (UART ↔ JTAG), JTAG bitstream loading,
QSPI flash bootstrap, board reload, and device status queries. This
is the low-level companion to icepi_helper.py — it manages the board
at the hardware/driver level rather than the protocol level.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from icepi.flash_service import DeviceSnapshot, probe_device, resolve_board_target
from icepi.tools import REPO_ROOT


ROOT = Path(__file__).resolve().parent
# Firmware/module/config data resolves through the bundled-aware repo root so an
# installed wheel (data under icepi/_bundled) works like a source checkout. ROOT
# itself stays next to this module, for the helper script and subprocess cwd.
DATA_ROOT = REPO_ROOT
HELPER_SCRIPT = ROOT / "icepi_helper.py"
LAYOUT_FILE = DATA_ROOT / "config" / "icepi-layout.json"
BOARD_LOCAL_CONFIG = DATA_ROOT / "config" / "board.local.json"
DEFAULT_PROJECT = "rime"
DEFAULT_BOARD_NAME = "icepi-zero"

COMMANDS = (
    "status",
    "info",
    "slots",
    "uart",
    "jtag",
    "build",
    "flash",
    "flash-qspi",
    "update",
    "verify",
    "bundle",
    "layout",
    "shell",
    "reload",
)

def print_step(text: str) -> None:
    print(f"[icepi] {text}")


def resolve_managed_path(explicit: str | None, env_name: str, default: Path) -> Path:
    raw = explicit or os.environ.get(env_name)
    candidate = Path(raw).expanduser() if raw else default
    resolved = candidate.resolve()
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def resolve_optional_board_config(explicit: str | None) -> Path | None:
    raw = explicit or os.environ.get("ICEPI_BOARD_CONFIG")
    if raw:
        candidate = Path(raw).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate
    if BOARD_LOCAL_CONFIG.exists():
        return BOARD_LOCAL_CONFIG.resolve()
    return None


def find_tool(name: str) -> str:
    from icepi.tools import find_oss_cad_tool
    found = find_oss_cad_tool(name, ROOT)
    if found:
        return found
    raise FileNotFoundError(
        f"{name} was not found. Set ICEPI_OSS_CAD_ROOT/ICEPI_OSS_CAD_BIN, keep OSS CAD Suite near the repo, or add it to PATH."
    )


def get_python() -> str:
    override = os.environ.get("ICEPI_PYTHON")
    if override:
        candidate = Path(override).expanduser()
        if candidate.exists():
            return str(candidate.resolve())
    if sys.executable:
        return sys.executable
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            return found
    raise FileNotFoundError("python was not found. Set ICEPI_PYTHON or add Python to PATH.")


def helper_base_args(args: argparse.Namespace) -> list[str]:
    base: list[str] = []
    if args.board_config_path is not None:
        base.extend(["--board-config", str(args.board_config_path)])
    base.extend(["--layout", str(args.layout_path)])
    return base


def invoke_helper(args: argparse.Namespace, helper_args: list[str]) -> None:
    env = os.environ.copy()
    previous_encoding = env.get("PYTHONIOENCODING")
    env["PYTHONIOENCODING"] = "utf-8"
    command = [get_python(), str(args.helper_path), *helper_base_args(args), *helper_args]
    try:
        subprocess.run(command, cwd=ROOT, check=True, env=env)
    finally:
        if previous_encoding is None:
            env.pop("PYTHONIOENCODING", None)
        else:
            env["PYTHONIOENCODING"] = previous_encoding


def invoke_build(args: argparse.Namespace, project: str) -> None:
    print_step(f"Building {project}")
    invoke_helper(args, ["build", project, "--clean"])


def get_bitstream_path(project: str) -> Path:
    # Standard project layout puts firmware images under firmware/images/<name>/
    # and experiments under experiments/<name>/. Try both.
    candidates = [
        Path.cwd() / "rime-build" / project / "bitstream.bit",  # installed-build output
        DATA_ROOT / "firmware" / "images" / project / "bitstream.bit",
        DATA_ROOT / "experiments" / project / "bitstream.bit",
        DATA_ROOT / "modules" / project / "bitstream.bit",
        DATA_ROOT / "firmware" / project / "bitstream.bit",  # legacy fall-back
    ]
    for bitstream in candidates:
        if bitstream.exists():
            return bitstream
    raise FileNotFoundError(candidates[0])


def quote_cmd_argument(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() or ch == '"' for ch in value):
        return '"' + value.replace('"', '""') + '"'
    return value


def run_loader_command(
    loader_args: list[str],
    *,
    check: bool,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    loader = Path(find_tool("openFPGALoader"))
    command = [str(loader), *loader_args]
    if os.name == "nt":
        env_bat = loader.parent.parent / "environment.bat"
        if env_bat.exists():
            cmdline = " ".join(
                [
                    "call",
                    quote_cmd_argument(str(env_bat)),
                    "&&",
                    quote_cmd_argument(str(loader)),
                    *[quote_cmd_argument(arg) for arg in loader_args],
                ]
            )
            return subprocess.run(
                ["cmd.exe", "/c", cmdline],
                cwd=ROOT,
                check=check,
                capture_output=capture_output,
                text=capture_output,
            )
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        capture_output=capture_output,
        text=capture_output,
    )


def invoke_loader(loader_args: list[str]) -> None:
    print_step("Running openFPGALoader")
    run_loader_command(loader_args, check=True, capture_output=False)


def parse_jtag_detect_output(text: str) -> dict[str, str] | None:
    info: dict[str, str] = {"board": DEFAULT_BOARD_NAME, "probe": "openFPGALoader"}
    found = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("idcode "):
            info["idcode"] = line.split(None, 1)[1]
            found = True
        elif lowered.startswith("manufacturer "):
            info["manufacturer"] = line.split(None, 1)[1]
            found = True
        elif lowered.startswith("family "):
            info["family"] = line.split(None, 1)[1]
            found = True
        elif lowered.startswith("model "):
            info["model"] = line.split(None, 1)[1]
            found = True
    return info if found else None


def probe_jtag_target() -> dict[str, str] | None:
    try:
        result = run_loader_command(
            ["-b", DEFAULT_BOARD_NAME, "--detect"],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        return None
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if result.returncode != 0:
        return None
    return parse_jtag_detect_output(text)


def explain_device(device: DeviceSnapshot) -> list[str]:
    lines = [f"Mode: {device.mode}"]
    if device.com_port:
        lines.append(f"Serial port: {device.com_port}")
    if device.driver:
        lines.append(f"Driver: {device.driver}")
    if device.friendly_name:
        lines.append(f"Device: {device.friendly_name}")
    if device.service:
        lines.append(f"Service: {device.service}")
    if device.instance_id:
        lines.append(f"Instance: {device.instance_id}")
    for note in device.notes:
        lines.append(f"Note: {note}")
    return lines


def probe_target(args: argparse.Namespace) -> DeviceSnapshot:
    target = resolve_board_target(path=args.board_config_path)
    return probe_device(target=target, baud=target.baud)


def wait_for_uart(args: argparse.Namespace, timeout: float = 20.0) -> DeviceSnapshot:
    deadline = time.monotonic() + timeout
    last_device: DeviceSnapshot | None = None
    while time.monotonic() < deadline:
        last_device = probe_target(args)
        if last_device.mode == "uart":
            return last_device
        time.sleep(0.25)
    raise RuntimeError(
        "UART mode did not become available. Set ICEPI_ADMIN_UART_COMMAND if this host needs an explicit handoff."
    )


def run_shell_hook(env_name: str, label: str) -> bool:
    command = os.environ.get(env_name)
    if not command:
        return False
    print_step(f"Running {label} hook")
    import shlex
    subprocess.run(shlex.split(command), cwd=ROOT, check=True)
    return True


DRIVER_CACHE = ROOT / "driver-cache"
WINUSB_INF = DRIVER_CACHE / "ft231x_winusb.inf"
VCP_BUS_INF = DRIVER_CACHE / "ftdibus.inf"
VCP_PORT_INF = DRIVER_CACHE / "ftdiport.inf"


def _pnputil_run(pnp_args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["pnputil"] + pnp_args,
        capture_output=True, text=True, check=False,
    )
    if check and result.returncode not in (0, 5, 3010):
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
    return result


def _pnputil_find_ftdi() -> tuple[str | None, str]:
    result = _pnputil_run(["/enum-devices", "/connected"], check=False)
    lines = result.stdout.splitlines()
    instance_id = None
    driver_class = "unknown"
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "VID_0403" in line and "PID_6015" in line and "Instance ID:" in line:
            instance_id = line.split(":", 1)[1].strip()
            for j in range(i + 1, min(i + 8, len(lines))):
                entry = lines[j].strip()
                if entry.startswith("Class Name:"):
                    cls = entry.split(":", 1)[1].strip()
                    driver_class = "vcp" if cls == "Ports" else "winusb" if cls == "USBDevice" else cls
                    break
            break
        i += 1
    return instance_id, driver_class


def _pnputil_switch_to_jtag() -> bool:
    if os.name != "nt" or not WINUSB_INF.exists():
        return False
    instance_id, driver_class = _pnputil_find_ftdi()
    if instance_id is None:
        return False
    if driver_class == "winusb":
        return True
    print_step("Switching FTDI to WinUSB (JTAG) via pnputil")
    _pnputil_run(["/remove-device", instance_id])
    _pnputil_run(["/add-driver", str(WINUSB_INF), "/install"])
    time.sleep(2)
    return True


def _pnputil_switch_to_uart() -> bool:
    if os.name != "nt" or not VCP_BUS_INF.exists():
        return False
    instance_id, driver_class = _pnputil_find_ftdi()
    if instance_id is None:
        _pnputil_run(["/scan-devices"], check=False)
        time.sleep(2)
        instance_id, driver_class = _pnputil_find_ftdi()
    if instance_id is None:
        return False
    if driver_class == "vcp":
        return True
    print_step("Switching FTDI to VCP (UART) via pnputil")
    _pnputil_run(["/remove-device", instance_id], check=False)
    result = _pnputil_run(["/enum-drivers"], check=False)
    drv_lines = result.stdout.splitlines()
    for idx, line in enumerate(drv_lines):
        if "ft231x_winusb" in line.lower():
            for back in range(max(0, idx - 3), idx):
                prev = drv_lines[back].strip()
                if prev.lower().startswith("published name:"):
                    oem = prev.split(":", 1)[1].strip()
                    if oem.startswith("oem") and oem.endswith(".inf"):
                        _pnputil_run(["/delete-driver", oem, "/force"], check=False)
    _pnputil_run(["/add-driver", str(VCP_BUS_INF), "/install"], check=False)
    _pnputil_run(["/add-driver", str(VCP_PORT_INF), "/install"], check=False)
    _pnputil_run(["/scan-devices"], check=False)
    time.sleep(3)
    _, cls = _pnputil_find_ftdi()
    if cls != "vcp":
        _pnputil_run(["/scan-devices"], check=False)
        time.sleep(3)
    return True


def ensure_uart_mode(args: argparse.Namespace) -> None:
    device = probe_target(args)
    if device.mode == "uart":
        return
    if run_shell_hook("ICEPI_ADMIN_UART_COMMAND", "UART"):
        wait_for_uart(args)
        return
    if _pnputil_switch_to_uart():
        wait_for_uart(args)
        return
    # No driver switch is needed where the same FTDI chip exposes UART
    # directly (Linux): after a JTAG cycle the tty re-enumerates on its own,
    # so wait for it rather than failing the way a missing Windows VCP would.
    wait_for_uart(args)


def ensure_jtag_mode(args: argparse.Namespace) -> None:
    if probe_jtag_target() is not None:
        return
    if run_shell_hook("ICEPI_ADMIN_JTAG_COMMAND", "JTAG"):
        return
    if _pnputil_switch_to_jtag():
        for attempt in range(6):
            time.sleep(2)
            if probe_jtag_target() is not None:
                return
    device = probe_target(args)
    if device.mode == "uart":
        raise RuntimeError(
            "Board is in UART/VCP mode but JTAG is required. "
            "Run from an elevated shell or set ICEPI_ADMIN_JTAG_COMMAND."
        )
    if device.mode == "missing":
        raise RuntimeError(
            "Board is not detected on any serial port. Check USB cable and connection."
        )
    print_step("No explicit JTAG handoff command is configured; continuing with the current host binding.")


def show_status(args: argparse.Namespace) -> None:
    device = probe_target(args)
    jtag = probe_jtag_target() if device.mode == "missing" else None
    print("Backend: portable")
    print(f"Layout: {args.layout_path}")
    if args.board_config_path is not None:
        print(f"Board config: {args.board_config_path}")
    if jtag is not None:
        print("Mode: jtag")
        print(f"Probe: {jtag['probe']}")
        print(f"Board: {jtag['board']}")
        if "idcode" in jtag:
            print(f"IDCODE: {jtag['idcode']}")
        if "manufacturer" in jtag:
            print(f"Manufacturer: {jtag['manufacturer']}")
        if "family" in jtag:
            print(f"Family: {jtag['family']}")
        if "model" in jtag:
            print(f"Model: {jtag['model']}")
        print("Note: JTAG is available, but the serial interface is not currently exposed.")
    else:
        for line in explain_device(device):
            print(line)
    uart_hook = "configured" if os.environ.get("ICEPI_ADMIN_UART_COMMAND") else "not configured"
    jtag_hook = "configured" if os.environ.get("ICEPI_ADMIN_JTAG_COMMAND") else "not configured"
    print(f"UART hook: {uart_hook}")
    print(f"JTAG hook: {jtag_hook}")


def run_command(args: argparse.Namespace) -> None:
    project = args.project
    command = args.command
    dry_run = getattr(args, "dry_run", False)

    if dry_run and command in ("flash", "flash-qspi", "update", "verify", "reload"):
        print_step(f"[dry-run] would run: {command} {project}")
        return

    if command == "status":
        show_status(args)
        return
    if command == "info":
        ensure_uart_mode(args)
        invoke_helper(args, ["info"])
        return
    if command == "slots":
        invoke_helper(args, ["slots"])
        return
    if command == "uart":
        ensure_uart_mode(args)
        show_status(args)
        return
    if command == "jtag":
        ensure_jtag_mode(args)
        show_status(args)
        return
    if command == "build":
        invoke_build(args, project)
        return
    if command == "flash":
        invoke_build(args, project)
        ensure_jtag_mode(args)
        bitstream = get_bitstream_path(project)
        print_step(f"Loading SRAM image {bitstream}")
        invoke_loader(["-b", DEFAULT_BOARD_NAME, str(bitstream)])
        ensure_uart_mode(args)
        show_status(args)
        return
    if command == "flash-qspi":
        invoke_build(args, project)
        ensure_jtag_mode(args)
        bitstream = get_bitstream_path(project)
        print_step(f"Programming full boot flash image {bitstream} (bootstrap/recovery path)")
        invoke_loader(["-b", DEFAULT_BOARD_NAME, str(bitstream), "--write-flash", "--verify"])
        ensure_uart_mode(args)
        show_status(args)
        return
    if command == "update":
        invoke_build(args, project)
        ensure_uart_mode(args)
        bitstream = get_bitstream_path(project)
        print_step("Updating the layout-defined boot slot over the resident service")
        invoke_helper(
            args,
            ["upload", str(bitstream), "--slot", "boot", "--reload", "--verbose"],
        )
        show_status(args)
        return
    if command == "verify":
        invoke_build(args, project)
        ensure_uart_mode(args)
        bitstream = get_bitstream_path(project)
        print_step(f"Verifying the layout-defined boot slot against {bitstream}")
        invoke_helper(args, ["--verbose", "flash-verify", str(bitstream), "--slot", "boot"])
        return
    if command == "bundle":
        invoke_build(args, project)
        bitstream = get_bitstream_path(project)
        bundle_path = bitstream.parent / "bitstream.icepi.bundle.bin"
        print_step(f"Generating bundle {bundle_path}")
        invoke_helper(
            args,
            ["bundle", str(bitstream), "--slot", "boot", "--output", str(bundle_path)],
        )
        return
    if command == "layout":
        invoke_helper(args, ["layout"])
        return
    if command == "shell":
        ensure_uart_mode(args)
        invoke_helper(args, ["shell"])
        return
    if command == "reload":
        ensure_jtag_mode(args)
        print_step("Reloading from flash")
        invoke_loader(["-b", DEFAULT_BOARD_NAME, "-r"])
        ensure_uart_mode(args)
        show_status(args)
        return
    raise ValueError(f"unknown command: {command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cross-platform RIME administrative wrapper")
    parser.add_argument(
        "--layout",
        help="path to the flash layout JSON",
    )
    parser.add_argument(
        "--board-config",
        help="path to a local board identity JSON",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=COMMANDS,
        default="status",
        help="admin command to run",
    )
    parser.add_argument(
        "project",
        nargs="?",
        default=DEFAULT_PROJECT,
        help="firmware project for build/flash/update commands",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be done without touching hardware",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.layout_path = resolve_managed_path(args.layout, "ICEPI_LAYOUT_FILE", LAYOUT_FILE)
    args.board_config_path = resolve_optional_board_config(args.board_config)
    args.helper_path = resolve_managed_path(None, "ICEPI_HELPER_SCRIPT", HELPER_SCRIPT)
    try:
        run_command(args)
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
