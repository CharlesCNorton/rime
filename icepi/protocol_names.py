"""Human-readable name tables for the RIME UART protocol.

Re-exports the name-lookup functions from icepi.protocol so callers
can import from any of: icepi.protocol, icepi.protocol_names, or
icepi.flash_service (backwards compatibility).
"""

from __future__ import annotations

from icepi.protocol import (  # noqa: F401
    auto_exit_reason_name,
    auto_progress_text,
    auto_result_name,
    auto_state_name,
    bundle_error_name,
    command_name,
    debug_flag_names,
    describe_state_code,
    error_name,
    sd_error_name,
    service_state_name,
    spi_op_name,
    verify_error_name,
)

__all__ = [
    "auto_exit_reason_name",
    "auto_progress_text",
    "auto_result_name",
    "auto_state_name",
    "bundle_error_name",
    "command_name",
    "debug_flag_names",
    "describe_state_code",
    "error_name",
    "sd_error_name",
    "service_state_name",
    "spi_op_name",
    "verify_error_name",
]
