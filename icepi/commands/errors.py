"""Error rendering and fix suggestions for RIME CLI."""

from __future__ import annotations

import subprocess

from icepi.commands.helpers import CommandParseError, ShellInputError
from icepi.flash_service import (
    ERR_BUNDLE,
    ERR_BUSY,
    ERR_RX_TIMEOUT,
    ERR_SD,
    ERR_VERIFY,
    FlashServiceDiscoveryError,
    FlashServiceError,
    FlashServiceProtocolError,
    FlashServiceRemoteError,
    FlashServiceTimeout,
    FlashServiceVerifyError,
)
from icepi.tools import uart_restore_hint

__all__ = ["render_error_lines", "suggest_fix"]


def render_error_lines(exc: Exception) -> list[str]:
    # KeyError's str() wraps the message in repr quotes; show the raw message.
    message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
    lines = [f"ERROR: {message}"]
    usage = getattr(exc, "usage", None)
    if usage:
        lines.append(usage)
    lines.extend(suggest_fix(exc))
    return lines


def suggest_fix(exc: Exception) -> list[str]:
    hints: list[str] = []
    if isinstance(exc, FlashServiceDiscoveryError):
        hints.append(uart_restore_hint())
        hints.append("Hint: set `board.local.json` or ICEPI_USB_INSTANCE/ICEPI_USB_SERIAL if target discovery is ambiguous.")
    elif isinstance(exc, FlashServiceTimeout):
        hints.append("Hint: the UART side went quiet. Retry once, then use `reload` if it stays silent.")
    elif isinstance(exc, FlashServiceRemoteError):
        if exc.code == ERR_BUSY:
            hints.append("Hint: the service was already handling a response. Wait a moment and retry.")
        if exc.code == ERR_RX_TIMEOUT:
            hints.append("Hint: a multi-byte command stalled mid-frame. Retry the command cleanly.")
        if exc.code == ERR_SD:
            hints.append("Hint: check `sd info`; if media is present but cold, run `sd init` before retrying.")
        if exc.code == ERR_BUNDLE:
            if exc.detail == 0x0A:
                hints.append("Hint: `sd install` will not rewrite the live boot slot from a bundle while that image is running.")
                hints.append("Hint: use `install` or `update` for the boot slot, or target a non-live flash slot for SD installs.")
            hints.append("Hint: inspect the candidate with `sd bundle <lba>` before retrying the install.")
            hints.append("Hint: use `sd-layout` to find raw staging space ahead of the first partition.")
            hints.append("Hint: regenerate the bundle with `bundle <project> --slot <slot>` if the header or layout is wrong.")
        if exc.code == ERR_VERIFY:
            hints.append("Hint: the board wrote the chunk but read back different bytes. Retry after `sd init`, then inspect `debug --enter-service` if it repeats.")
    elif isinstance(exc, FlashServiceVerifyError):
        hints.append("Hint: the flash readback did not match. Re-run the command with `--trace` before trusting the image.")
    elif isinstance(exc, FlashServiceProtocolError):
        message = str(exc).lower()
        if "autonomous startup recovery" in message:
            hints.append("Hint: the board is busy in startup recovery. Use `status` to watch it or `reload` to abort.")
            hints.append("Hint: if startup recovery drops back to app mode with a failsafe version, inspect `sd-auto-info` before retrying.")
        if "service mode" in message or "service handoff failed" in message or "expected service firmware" in message:
            hints.append("Hint: add `--enter-service`, run `probe --enter-service`, or use `reload` if the resident app looks confused.")
        hints.append("Hint: the board and helper disagree on the wire protocol. Probe first, then reload if needed.")
    elif isinstance(exc, subprocess.CalledProcessError):
        hints.append("Hint: the build or reload subprocess failed. Read the tool output above and retry with a clean build if needed.")
    elif isinstance(exc, FlashServiceError):
        message = str(exc).lower()
        if "rime bundle header" in message:
            hints.append("Hint: point at the bundle's starting LBA, not the manifest or payload blocks.")
            hints.append("Hint: use `sd-layout` to find raw staging space ahead of the first partition.")
            hints.append("Hint: create a bundle with `bundle <project> --slot <slot>` before copying it onto the card.")
    elif isinstance(exc, FileNotFoundError):
        message = str(exc)
        if "has no bitstream yet" in message:
            hints.append("Hint: build the project first with `build <project>` or retry with `--build`.")
        else:
            hints.append("Hint: verify the path or run `build --list` to see known firmware projects.")
    elif isinstance(exc, KeyError):
        hints.append("Hint: run `slots` or `slot list` to list valid slot names and aliases.")
    elif isinstance(exc, ShellInputError):
        if "unterminated quote" in str(exc):
            hints.append('Hint: close the quote or remove it; quote multi-word paths like `"path with spaces/file.bit"`.')
        elif "trailing backslash" in str(exc):
            hints.append(r"Hint: quote Windows paths that end with `\`, or add another `\` before pressing Enter.")
        else:
            hints.append("Hint: quote multi-word arguments and check shell escaping before retrying.")
    elif isinstance(exc, CommandParseError):
        hints.append("Hint: run `help` in the shell or `--help` on the command for the expected arguments.")
    elif isinstance(exc, ValueError):
        message = str(exc).lower()
        if "raw sd gap" in message or "staging" in message:
            hints.append("Hint: run `sd layout` to inspect safe raw staging regions on the current card.")
        hints.append("Hint: run `help` in the shell or `--help` on the command for the expected arguments.")
    return hints
