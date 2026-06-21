"""Interactive RIME shell.

The shell is one live, mode-stable session over a single connection. Builtins
(`watch`, `use`, `x`/`sx`, `raw`, `map`, `bench`, `script`/`record`/`replay`)
exploit state, persistence, and in-place refresh that a one-shot CLI cannot.
Board/flash/SD commands mirror the CLI but run over the session's open
connection (via the pinned service in helpers), so service mode is entered once
and held across commands instead of re-dialed per command.
"""

from __future__ import annotations
from typing import Any

import argparse
import os
import sys
import time

from icepi.commands.helpers import (
    CommandParseError,
    ShellInputError,
    clear_session_service,
    explain_snapshot,
    load_layout_from_args,
    render_hexdump,
    render_sd_info_lines,
    set_session_service,
)
from icepi.protocol import MODE_SERVICE

__all__ = [
    "shell_help_lines",
    "split_shell_words",
    "translate_shell_words",
    "shell_prefix",
    "run_shell_line",
    "cmd_shell",
    "ShellSession",
    "SHELL_PROMPT",
    "SHELL_BANNER",
]

SHELL_PROMPT = "RIME> "
SHELL_BANNER = [
    "               *  *  *",
    "                \\ | /",
    "                 \\|/",
    "           *------*------*",
    "                 /|\\",
    "                / | \\",
    "               *  *  *",
    "",
    "               R I M E",
    "Resident IcePi Management Environment",
    "      interactive control shell",
    "  ECP5 | QSPI flash | SD | recovery",
    "'help' lists commands  |  'quit' exits",
]


def _format_uptime(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m {secs}s"
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


# ---- word splitting / friendly-form translation (shared with batch mode) ----

def split_shell_words(line: str) -> list[str]:
    words: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and in_quote != "'":
            current.append(line[i + 1])
            i += 2
            continue
        if ch == "\\" and i + 1 >= len(line):
            raise ShellInputError("trailing backslash")
        if in_quote is not None:
            if ch == in_quote:
                in_quote = None
            else:
                current.append(ch)
            i += 1
            continue
        if ch in ('"', "'"):
            in_quote = ch
            i += 1
            continue
        if ch in (" ", "\t"):
            if current:
                words.append("".join(current))
                current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    if in_quote is not None:
        raise ShellInputError("unterminated quote")
    if current:
        words.append("".join(current))
    return words


_FLASH_SUBS: set[str] = {"jedec", "status", "clear-error", "read", "verify"}
_SD_SUBS: set[str] = {"info", "init", "layout", "read", "install"}
_SERVICE_SUBS: set[str] = {"probe", "status", "doctor", "clear-error", "reload", "debug"}
_SLOT_AWARE: set[str] = {"install", "upload", "inspect", "flash-verify", "bundle", "sd-stage-bundle"}
_TARGET_AWARE: set[str] = {"install", "upload", "inspect", "flash-verify", "bundle", "sd-stage-bundle"}


def _translate_flash(rest: list[str]) -> list[str]:
    if not rest:
        return ["flash-read", "0", "16"]
    sub = rest[0].lower()
    if sub in _FLASH_SUBS:
        return [f"flash-{sub}"] + rest[1:]
    return ["flash-read"] + rest


def _translate_sd(rest: list[str]) -> list[str]:
    if not rest:
        return ["sd-info"]
    sub = rest[0].lower()
    if sub == "fs":
        return [f"sd-fs-{rest[1].lower()}"] + rest[2:] if len(rest) >= 2 else ["sd-fs-info"]
    if sub in ("auto", "boot"):
        return [f"sd-auto-{rest[1].lower()}"] + rest[2:] if len(rest) >= 2 else ["sd-auto-info"]
    if sub == "stage":
        return ["sd-stage-bundle"] + rest[1:]
    if sub in _SD_SUBS:
        return [f"sd-{sub}"] + rest[1:]
    if sub == "bundle":
        return ["sd-bundle-info"] + rest[1:]
    return ["sd-info"] + rest


def translate_shell_words(words: list[str]) -> list[str]:
    if not words:
        return []
    head = words[0].lower()
    rest = words[1:]
    if head == "slot" and rest and rest[0] in ("show", "list"):
        return (["slots"] if rest[0] == "list" else ["slot-show"]) + rest[1:]
    if head == "flash":
        return _translate_flash(rest)
    if head == "sd":
        return _translate_sd(rest)
    if head == "bundle" and rest and rest[0].lower() == "create":
        return ["bundle"] + rest[1:]
    if head == "project" and rest and rest[0].lower() == "list":
        return ["build", "--list"] + rest[1:]
    if head == "board":
        return (["board-test"] + rest[1:]) if rest and rest[0].lower() == "test" else ["probe"] + rest
    if head == "service":
        if rest and rest[0].lower() in _SERVICE_SUBS:
            return [rest[0].lower()] + rest[1:]
        sub = rest[0].lower() if rest else ""
        if sub in ("enter", ""):
            return ["info", "--enter-service"]
        if sub == "exit":
            return ["probe"]
        return ["info", "--enter-service"] + rest
    return [head] + rest


def shell_prefix(args: argparse.Namespace) -> list[str]:
    prefix: list[str] = []
    for flag, attr in (("--board-config", "board_config"), ("--port", "port"),
                       ("--baud", "baud"), ("--layout", "layout")):
        val = getattr(args, attr, None)
        if val is not None and val != "":
            prefix.extend([flag, str(val)])
    for flag, attr in (("--verbose", "verbose"), ("--trace", "trace"), ("--summary-json", "summary_json")):
        if getattr(args, attr, False):
            prefix.append(flag)
    return prefix


# ---- help, generated from the CLI parser (single source of truth) ----

_BUILTIN_HELP: dict[str, tuple[str, str]] = {
    "watch": ("watch <status|sd|stats|debug|map> [secs]", "Live, in-place refresh of a board view (Ctrl-C to stop)."),
    "use": ("use <slot|alias> | use target <name> | use clear", "Set a session default slot/target for later commands."),
    "ctx": ("ctx", "Show the current session context."),
    "x": ("x [addr] [len]  |  n  |  p  |  /<hex>", "Browse flash: hexdump, page next/prev, search bytes."),
    "sx": ("sx [lba] [count]", "Hexdump SD blocks."),
    "raw": ("raw <hex> [hex ...]", "Send raw bytes to the service FSM and print the reply."),
    "map": ("map", "Scan flash and print a sector map (# data, ~ partial, . blank)."),
    "bench": ("bench [uart|flash|sdram|stream|all]", "Measure subsystem throughput."),
    "whoami": ("whoami", "Show board identity, mode, and uptime."),
    "uptime": ("uptime", "Show time since last boot."),
    "script": ("script <file>", "Run shell commands from a file over the live connection."),
    "record": ("record [file] | record stop", "Record typed commands; replay re-runs them."),
    "replay": ("replay [file]", "Replay recorded commands."),
    "help": ("help [command]", "Show commands, or detail for one."),
    "quit": ("quit | exit", "Leave the shell."),
}


def _cli_commands() -> dict[str, str]:
    try:
        from icepi_helper import build_parser
        parser = build_parser()
        for action in parser._actions:                      # noqa: SLF001
            choices = getattr(action, "_choices_actions", None)
            if choices:
                return {ca.dest: (ca.help or "") for ca in choices}
    except Exception:
        pass
    return {}


def shell_help_lines(topic: str | None = None) -> list[str]:
    cli = _cli_commands()
    if topic is not None:
        key = topic.strip().lower()
        if key in _BUILTIN_HELP:
            return list(_BUILTIN_HELP[key])
        if key in cli:
            return [key, f"    {cli[key]}"]
        return [f"Unknown help topic: {topic}", "Type `help` for the command list."]
    lines = ["Session commands (live connection; not in the one-shot CLI):"]
    for usage, desc in _BUILTIN_HELP.values():
        lines.append(f"  {usage}")
        lines.append(f"      {desc}")
    lines.append("")
    lines.append("Board / flash / SD commands (run over the session):")
    for name, desc in cli.items():
        lines.append(f"  {name:<16} {desc}")
    lines.append("")
    lines.append("Friendly forms: slot show | flash read | sd info | sd fs ls | bundle create")
    lines.append("Type `help <command>` for one command.")
    return lines


# ---- the existing live builtins (raw / whoami / uptime / bench) ----

def _run_builtin(words: list[str], svc: Any) -> bool:
    cmd = words[0]
    args = words[1:]

    if cmd == "uptime":
        try:
            print(f"Uptime: {_format_uptime(svc.uptime())}")
        except Exception as exc:
            print(f"Error: {exc}")
        return True

    if cmd == "whoami":
        try:
            ident = svc.identity()
            mode = "app" if ident["app_mode"] else "service"
            print(f"{ident['name']}")
            print(f"Mode: {mode}")
            print(f"Uptime: {_format_uptime(svc.uptime())}")
            print(f"Port: {svc.port_name}")
        except Exception as exc:
            print(f"Error: {exc}")
        return True

    if cmd == "raw":
        if not args:
            print("Usage: raw <hex-byte> [hex-byte ...]   e.g. raw 0x00 (HELLO), raw 01 (PING)")
            return True
        try:
            payload = bytes([int(b, 0) for b in args])
            from icepi.flash_service import command_name
            frame = svc.raw_exchange(payload, timeout=2.0, allow_empty=True)
            tx_hex = " ".join(f"{b:02X}" for b in payload)
            rx_hex = " ".join(f"{b:02X}" for b in frame) if frame else "<empty>"
            print(f"TX [{command_name(payload[0])}]: {tx_hex}")
            print(f"RX [{len(frame):2d}]:    {rx_hex}")
            if frame:
                print("           " + "".join(chr(b) if 32 <= b < 127 else "." for b in frame))
        except Exception as exc:
            print(f"Error: {exc}")
        return True

    if cmd == "bench":
        _bench(svc, args[0] if args else "all")
        return True

    return False


def _bench(svc: Any, target: str) -> None:
    try:
        need_enter = svc.mode() != MODE_SERVICE
        if need_enter:
            svc.enter_service_mode()
        if target in ("uart", "all"):
            count = 200
            t0 = time.perf_counter()
            for _ in range(count):
                svc.ping()
            el = time.perf_counter() - t0
            print(f"UART:  {count/el:.0f} round-trips/s, {el/count*1000:.1f} ms/round-trip ({count} PINGs)")
        if target in ("flash", "all"):
            count = 100
            t0 = time.perf_counter()
            for i in range(count):
                svc.read16(i * 16)
            el = time.perf_counter() - t0
            print(f"Flash: {count*16/el:.0f} bytes/s read ({count*16/el/1024:.1f} KB/s, {count} chunks)")
        if target in ("sdram", "all"):
            pat = bytes(range(16))
            count = 100
            t0 = time.perf_counter()
            for _ in range(count):
                svc.sdram_write16(0x280000, pat)
                svc.sdram_read16(0x280000)
            el = time.perf_counter() - t0
            print(f"SDRAM: {count/el:.0f} write+read pairs/s ({count} pairs)")
        if target in ("stream", "all"):
            for sz in (1024, 4096, 16384, 32768):
                payload = bytes([(i * 37) & 0xFF for i in range(sz)])
                t0 = time.perf_counter()
                svc.sdram_write_stream(0, payload, timeout=30.0)
                el = time.perf_counter() - t0
                print(f"Stream: {sz/el/1024:.1f} KB/s @ {sz} bytes ({el*1000:.0f} ms)")
        if need_enter:
            svc.exit_service_mode()
    except Exception as exc:
        print(f"Error: {exc}")


def _map_lines(svc: Any) -> list[str]:
    info = svc.info()
    flash_size = 1 << (info.addr_bytes * 8) if info.addr_bytes <= 3 else 0x1000000
    sector = info.erase_size
    sectors = flash_size // sector
    out = [f"Flash: {flash_size // 1024} KB, {sectors} sectors of {sector // 1024} KB", ""]
    row_sectors = 16
    row_bytes = row_sectors * sector
    rows = (sectors + row_sectors - 1) // row_sectors
    out.append("           " + "".join(f"{c:X}" for c in range(row_sectors)))
    out.append("           " + "-" * row_sectors)
    tb = tp = tf = 0
    for row in range(rows):
        base = row * row_bytes
        line = f"0x{base:06X} |"
        for col in range(row_sectors):
            addr = base + col * sector
            if addr >= flash_size:
                line += " "
                continue
            bh = svc.read16(addr) == b"\xFF" * 16
            bt = svc.read16(addr + sector - 16) == b"\xFF" * 16
            if bh and bt:
                line += "."; tb += 1
            elif not bh and not bt:
                line += "#"; tf += 1
            else:
                line += "~"; tp += 1
        out.append(line + f"| 0x{base + row_bytes - 1:06X}")
    out += ["", "Legend: # data  ~ partial  . blank",
            f"Sectors: {tf} data, {tp} partial, {tb} blank"]
    return out


# ---- the live session ----

class ShellSession:
    def __init__(self, svc: Any, args: argparse.Namespace, run_fn: Any, parser_fn: Any) -> None:
        self.svc = svc
        self.args = args
        self.run_fn = run_fn
        self.parser_fn = parser_fn
        self.slot: str | None = None
        self.target: str | None = None
        self.last_addr = 0
        self.last_len = 256
        self.last_lba = 0
        self.recording: list[str] | None = None
        self.recording_file: str | None = None
        self.recorded: list[str] = []

    # -- service-mode helper --
    def _ensure_service(self) -> bool:
        if self.svc is None:
            raise RuntimeError("board not connected")
        if self.svc.mode() != MODE_SERVICE:
            self.svc.enter_service_mode()
            return True
        return False

    # -- dispatch --
    def run_line(self, line: str) -> bool:
        try:
            words = split_shell_words(line)
        except ShellInputError as exc:
            print(f"Error: {exc}")
            return True
        if not words:
            return True
        head = words[0].lower()
        if head in ("quit", "exit"):
            return False
        if head in ("help", "?"):
            for ln in shell_help_lines(" ".join(words[1:]) or None):
                print(ln)
            return True
        if self.recording is not None and head not in ("record", "replay", "script", "quit", "exit", "help", "?"):
            self.recording.append(line.strip())
        if head == "watch":
            self._watch(words[1:]); return True
        if head == "use":
            self._use(words[1:]); return True
        if head == "ctx":
            self._ctx(); return True
        if head in ("x", "n", "p"):
            self._browse_flash(head, words[1:]); return True
        if head == "sx":
            self._browse_sd(words[1:]); return True
        if line.lstrip().startswith("/"):
            self._search(line.lstrip()[1:]); return True
        if head == "script":
            self._script(words[1:]); return True
        if head == "record":
            self._record(words[1:]); return True
        if head == "replay":
            self._replay(words[1:]); return True
        if head == "map":
            self._guarded(lambda: [print(ln) for ln in _map_lines(self.svc)], service=True); return True
        if head in ("uptime", "whoami", "raw", "bench"):
            if self.svc is None:
                print("board not connected"); return True
            _run_builtin(words, self.svc); return True
        return self._dispatch_cli(words)

    def _guarded(self, fn: Any, *, service: bool = False) -> None:
        if self.svc is None:
            print("board not connected"); return
        entered = False
        try:
            if service:
                entered = self._ensure_service()
            fn()
        except KeyboardInterrupt:
            print()
        except Exception as exc:
            print(f"Error: {exc}")
        finally:
            if entered:
                try:
                    self.svc.exit_service_mode()
                except Exception:
                    pass

    # -- CLI commands over the session connection --
    def _dispatch_cli(self, words: list[str]) -> bool:
        translated = translate_shell_words(words)
        if not translated:
            return True
        translated = self._inject_context(translated)
        full = shell_prefix(self.args) + translated
        if self.svc is not None:
            set_session_service(self.svc)
        try:
            parsed = self.parser_fn().parse_args(full)
            self.run_fn(parsed)
        except SystemExit:
            pass
        except CommandParseError as exc:
            print(f"Error: {exc}")
            if exc.usage:
                print(exc.usage)
        except Exception as exc:
            print(f"Error: {exc}")
        finally:
            clear_session_service()
        if translated[0] == "reload" or "--reload" in translated:
            self._reconnect()
        return True

    def _inject_context(self, translated: list[str]) -> list[str]:
        cmd = translated[0]
        out = list(translated)
        if self.target and cmd in _TARGET_AWARE and (len(out) == 1 or out[1].startswith("-")):
            out.insert(1, self.target)
        if self.slot and cmd in _SLOT_AWARE and "--slot" not in out:
            out += ["--slot", self.slot]
        return out

    def _reconnect(self) -> None:
        if self.svc is None:
            return
        try:
            self.svc.close()
        except Exception:
            pass
        for _ in range(12):
            time.sleep(0.5)
            try:
                self.svc.open()
                self.svc.mode()
                return
            except Exception:
                continue
        print("  (connection lost after reload; re-enter the shell if commands fail)")

    # -- watch --
    def _watch(self, args: list[str]) -> None:
        topic = (args[0].lower() if args else "status")
        secs = float(args[1]) if len(args) > 1 else 1.0
        once = not sys.stdin.isatty()
        self._guarded(lambda: self._watch_loop(topic, secs, once),
                      service=topic in ("sd", "stats", "debug", "map"))

    def _watch_loop(self, topic: str, secs: float, once: bool) -> None:
        while True:
            sys.stdout.write("\033[2J\033[H")
            print(f"watch {topic}  ({time.strftime('%H:%M:%S')})   Ctrl-C to stop\n")
            for ln in self._watch_render(topic):
                print(ln)
            sys.stdout.flush()
            if once:
                break
            time.sleep(secs)

    def _watch_render(self, topic: str) -> list[str]:
        svc = self.svc
        if topic == "status":
            return explain_snapshot(svc.probe(auto_enter=False))
        if topic == "sd":
            return render_sd_info_lines(svc.sd_info())
        if topic == "stats":
            s = svc.stats()
            return [f"cmds={s.command_count}  erase={s.erase_count}  program={s.program_count}  errors={s.error_count}"]
        if topic == "debug":
            d = svc.debug()
            return [f"state={d.state_name}  cmd={d.current_cmd_name}  spi={d.spi_op_name}",
                    f"flags={','.join(d.flag_names) or 'clear'}",
                    f"auto={d.auto_state_name}  exit={d.auto_exit_reason_name}  progress={d.auto_progress_text}"]
        if topic == "map":
            return _map_lines(svc)
        return [f"unknown watch topic: {topic}  (status|sd|stats|debug|map)"]

    # -- session context --
    def _use(self, args: list[str]) -> None:
        if not args:
            print("usage: use <slot|alias> | use target <name> | use clear"); return
        first = args[0].lower()
        if first == "clear":
            self.slot = self.target = None; print("context cleared"); return
        if first == "target" and len(args) > 1:
            self.target = args[1]; print(f"target = {self.target}"); return
        name = args[1] if first == "slot" and len(args) > 1 else args[0]
        try:
            load_layout_from_args(self.args).resolve_slot(name)
            self.slot = name
            print(f"slot = {name}")
        except Exception:
            self.target = name
            print(f"target = {name}  (not a known slot; set as target)")

    def _ctx(self) -> None:
        print(f"slot:   {self.slot or '(none)'}")
        print(f"target: {self.target or '(none)'}")
        print(f"flash:  last 0x{self.last_addr:06X}  (+{self.last_len} bytes)")
        print(f"sd:     last LBA {self.last_lba}")
        rec = "off" if self.recording is None else f"{len(self.recording)} lines"
        print(f"record: {rec}")

    # -- flash / sd browser --
    def _browse_flash(self, cmd: str, args: list[str]) -> None:
        if cmd == "x":
            if args:
                self.last_addr = int(args[0], 0)
            if len(args) > 1:
                self.last_len = max(16, int(args[1], 0))
        elif cmd == "n":
            self.last_addr += self.last_len
        elif cmd == "p":
            self.last_addr = max(0, self.last_addr - self.last_len)

        def show() -> None:
            data = b"".join(self.svc.read16(self.last_addr + o) for o in range(0, self.last_len, 16))
            for ln in render_hexdump(data[:self.last_len], base_address=self.last_addr):
                print(ln)
        self._guarded(show, service=True)

    def _browse_sd(self, args: list[str]) -> None:
        if args:
            self.last_lba = int(args[0], 0)
        count = int(args[1], 0) if len(args) > 1 else 1

        def show() -> None:
            for i in range(count):
                data = self.svc.sd_read(self.last_lba + i, offset=0, length=512)
                print(f"LBA {self.last_lba + i}:")
                for ln in render_hexdump(data, base_address=0):
                    print(ln)
            self.last_lba += count
        self._guarded(show, service=True)

    def _search(self, rest: str) -> None:
        try:
            needle = bytes.fromhex(rest.strip().replace(" ", ""))
        except ValueError:
            print("usage: /<hex bytes>   e.g. /BDB3"); return
        if not needle:
            return

        def scan() -> None:
            start = self.last_addr
            limit = start + 0x100000
            window = b""
            a = start
            while a < limit:
                window += self.svc.read16(a)
                a += 16
                idx = window.find(needle)
                if idx >= 0:
                    found = a - len(window) + idx
                    print(f"found at 0x{found:06X}")
                    self.last_addr = found & ~0xF
                    return
                if len(window) > len(needle):
                    window = window[-len(needle):]
            print(f"not found in 0x{start:06X}..0x{limit:06X}")
        self._guarded(scan, service=True)

    # -- script / record / replay --
    def _run_seq(self, lines: list[str]) -> None:
        for raw in lines:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            print(f"{SHELL_PROMPT}{s}")
            if not self.run_line(s):
                break

    def _script(self, args: list[str]) -> None:
        if not args:
            print("usage: script <file>"); return
        try:
            text = open(os.path.expanduser(args[0]), encoding="utf-8").read()
        except OSError as exc:
            print(f"Error: {exc}"); return
        self._run_seq(text.splitlines())

    def _record(self, args: list[str]) -> None:
        if args and args[0].lower() in ("stop", "off"):
            self.recorded = list(self.recording or [])
            if self.recording_file and self.recorded:
                try:
                    open(self.recording_file, "w", encoding="utf-8").write("\n".join(self.recorded) + "\n")
                    print(f"recorded {len(self.recorded)} lines to {self.recording_file}")
                except OSError as exc:
                    print(f"Error: {exc}")
            else:
                print(f"recorded {len(self.recorded)} lines (use `replay`)")
            self.recording = None
            self.recording_file = None
            return
        self.recording = []
        self.recording_file = os.path.expanduser(args[0]) if args else None
        print("recording... type `record stop` to finish")

    def _replay(self, args: list[str]) -> None:
        if args:
            try:
                lines = open(os.path.expanduser(args[0]), encoding="utf-8").read().splitlines()
            except OSError as exc:
                print(f"Error: {exc}"); return
        else:
            lines = self.recorded
        if not lines:
            print("nothing to replay"); return
        self._run_seq(lines)


# ---- back-compat shim + completion + entry point ----

def run_shell_line(line: str, args: argparse.Namespace, run_fn: Any, parser_fn: Any, *, svc: Any = None) -> bool:
    return ShellSession(svc, args, run_fn, parser_fn).run_line(line)


def _all_command_names(cli: dict[str, str]) -> list[str]:
    friendly = ["slot", "flash", "sd", "bundle", "project", "board", "service"]
    return sorted(set(list(_BUILTIN_HELP) + list(cli) + friendly + ["n", "p"]))


def _slot_names(args: argparse.Namespace) -> list[str]:
    try:
        layout = load_layout_from_args(args)
        return sorted(set(list(layout.slots) + list(layout.aliases)))
    except Exception:
        return []


def _project_names() -> list[str]:
    try:
        from icepi.build import available_projects
        return list(available_projects())
    except Exception:
        return []


def _module_names() -> list[str]:
    try:
        from icepi.tools import REPO_ROOT
        root = REPO_ROOT / "modules"
        return sorted(d.name for d in root.iterdir() if (d / "module.json").exists())
    except Exception:
        return []


def _setup_readline(args: argparse.Namespace) -> None:
    try:
        import readline
    except Exception:
        return
    cli = _cli_commands()
    commands = _all_command_names(cli)
    slots = _slot_names(args)
    targets = _project_names() + _module_names()

    def completer(text: str, state: int) -> str | None:
        buf = readline.get_line_buffer()
        toks = buf[:readline.get_endidx()].split()
        if len(toks) <= 1 and not buf.endswith(" "):
            pool = commands
        else:
            head = toks[0].lower()
            if "--slot" in toks or head in ("slot", "use") or head == "swap":
                pool = slots + targets if head == "swap" else slots
            elif head in ("install", "inspect", "build", "compose", "profile",
                          "flash-verify", "upload", "bundle"):
                pool = targets
            else:
                pool = slots + targets
        opts = [c for c in pool if c.startswith(text)]
        return opts[state] if state < len(opts) else None

    readline.set_completer(completer)
    readline.set_completer_delims(" \t")
    readline.parse_and_bind("tab: complete")
    hist = os.path.expanduser("~/.rime_history")
    try:
        readline.read_history_file(hist)
    except OSError:
        pass
    import atexit

    def _save() -> None:
        try:
            readline.set_history_length(1000)
            readline.write_history_file(hist)
        except OSError:
            pass
    atexit.register(_save)


def cmd_shell(args: argparse.Namespace) -> dict[str, object]:
    from icepi_helper import build_parser, run_command, FriendlyArgumentParser
    from icepi.commands.helpers import make_service

    def run_fn(parsed: argparse.Namespace) -> None:
        run_command(parsed)

    def parser_fn() -> argparse.ArgumentParser:
        return build_parser(FriendlyArgumentParser)

    if hasattr(args, "shell_commands") and args.shell_commands:
        svc = None
        try:
            svc = make_service(args)
            svc.open()
        except Exception:
            svc = None
        session = ShellSession(svc, args, run_fn, parser_fn)
        for command_line in args.shell_commands:
            session.run_line(command_line)
        if svc is not None:
            svc.close()
        return {"shell": "batch", "commands": args.shell_commands}

    for line in SHELL_BANNER:
        print(line)
    print()

    svc = None
    try:
        svc = make_service(args)
        svc.open()
        try:
            ident = svc.identity()
            mode = "app" if ident["app_mode"] else "service"
            print(f"  {ident['name']} on {svc.port_name} | {mode} | up {_format_uptime(svc.uptime())}")
        except Exception:
            print(f"  connected to {svc.port_name}")
        print()
    except Exception as exc:
        print(f"  board not available: {exc}")
        print()

    _setup_readline(args)
    session = ShellSession(svc, args, run_fn, parser_fn)
    while True:
        try:
            raw = input(SHELL_PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not session.run_line(raw):
            break
    if svc is not None:
        svc.close()
    return {"shell": "interactive"}
