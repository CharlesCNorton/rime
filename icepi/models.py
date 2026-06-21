"""Domain model dataclasses and protocol constants for RIME."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "BUNDLE_MAGIC",
    "BUNDLE_HEADER_BYTES",
    "AUTO_MAGIC",
    "AUTO_CONTROL_LBA",
    "AUTO_CONTROL_BYTES",
    "AUTO_FLAG_ARMED",
    "AUTO_FLAG_CLEAR_ON_SUCCESS",
    "AUTO_FLAG_ALLOW_FALLBACK",
    "AUTO_FLAG_FALLBACK_ON_FAIL",
    "AUTO_RESULT_LABELS",
    "FlashSlot",
    "LayoutConfig",
    "ImagePlan",
    "BundleHeader",
    "AutoControlBlock",
    "ResolvedBitstream",
    "compute_auto_control_checksum",
]


BUNDLE_MAGIC = b"ICEPIB1\x00"
BUNDLE_HEADER_BYTES = 512


AUTO_MAGIC = b"RIMEAUTO"
AUTO_CONTROL_LBA = 1
AUTO_CONTROL_BYTES = 64

AUTO_FLAG_ARMED = 1 << 0
AUTO_FLAG_CLEAR_ON_SUCCESS = 1 << 1
AUTO_FLAG_ALLOW_FALLBACK = 1 << 2
AUTO_FLAG_FALLBACK_ON_FAIL = 1 << 3

AUTO_RESULT_NONE = 0
AUTO_RESULT_PENDING = 1
AUTO_RESULT_RUNNING_PRIMARY = 2
AUTO_RESULT_RUNNING_FALLBACK = 3
AUTO_RESULT_SUCCESS_PRIMARY = 4
AUTO_RESULT_SUCCESS_FALLBACK = 5
AUTO_RESULT_FAIL_PRIMARY = 6
AUTO_RESULT_FAIL_FALLBACK = 7
AUTO_RESULT_EXHAUSTED = 8
AUTO_RESULT_INVALID = 9

AUTO_RESULT_LABELS = {
    AUTO_RESULT_NONE: "none",
    AUTO_RESULT_PENDING: "pending",
    AUTO_RESULT_RUNNING_PRIMARY: "running-primary",
    AUTO_RESULT_RUNNING_FALLBACK: "running-fallback",
    AUTO_RESULT_SUCCESS_PRIMARY: "success-primary",
    AUTO_RESULT_SUCCESS_FALLBACK: "success-fallback",
    AUTO_RESULT_FAIL_PRIMARY: "fail-primary",
    AUTO_RESULT_FAIL_FALLBACK: "fail-fallback",
    AUTO_RESULT_EXHAUSTED: "exhausted",
    AUTO_RESULT_INVALID: "invalid",
}



@dataclass(slots=True)
class FlashSlot:
    name: str
    offset: int
    size: int
    bootable: bool = False
    writable: bool = True
    description: str | None = None
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @property
    def end(self) -> int:
        return self.offset + self.size

    def fits(self, size_bytes: int) -> bool:
        return size_bytes <= self.size

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "offset": self.offset,
            "size": self.size,
            "end": self.end,
            "bootable": self.bootable,
            "writable": self.writable,
            "description": self.description,
            "aliases": list(self.aliases),
            "tags": list(self.tags),
        }


@dataclass(slots=True)
class LayoutConfig:
    path: Path
    flash_size: int
    default_slot: str
    bundle_block_size: int
    slots: dict[str, FlashSlot]
    aliases: dict[str, str]

    def resolve_slot(self, name: str | None = None) -> FlashSlot:
        wanted = (name or self.default_slot).strip().lower()
        canonical = self.aliases.get(wanted, wanted)
        if canonical not in self.slots:
            known = ", ".join(sorted(self.aliases))
            raise KeyError(f"unknown slot `{wanted}` (known: {known})")
        return self.slots[canonical]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "flash_size": self.flash_size,
            "default_slot": self.default_slot,
            "bundle_block_size": self.bundle_block_size,
            "aliases": self.aliases,
            "slots": {name: slot.as_dict() for name, slot in self.slots.items()},
        }



@dataclass(slots=True)
class ImagePlan:
    bitstream_path: Path
    slot_name: str | None
    address: int
    reserved_bytes: int | None
    bitstream_bytes: int
    padded_bytes: int
    erase_bytes: int
    chunk_size: int
    erase_size: int
    block_size: int
    crc32: int
    sha256: str
    bootable: bool

    @property
    def end_address(self) -> int:
        return self.address + self.padded_bytes

    def as_dict(self) -> dict[str, Any]:
        return {
            "bitstream_path": str(self.bitstream_path),
            "slot_name": self.slot_name,
            "address": self.address,
            "reserved_bytes": self.reserved_bytes,
            "bitstream_bytes": self.bitstream_bytes,
            "padded_bytes": self.padded_bytes,
            "erase_bytes": self.erase_bytes,
            "chunk_size": self.chunk_size,
            "erase_size": self.erase_size,
            "block_size": self.block_size,
            "crc32": f"0x{self.crc32:08X}",
            "sha256": self.sha256,
            "bootable": self.bootable,
            "end_address": self.end_address,
        }



@dataclass(slots=True)
class BundleHeader:
    magic: bytes
    reserved: int
    block_size: int
    manifest_bytes: int
    image_offset: int
    image_bytes: int
    image_padded: int
    target_address: int
    reserved_bytes: int
    crc32: int
    sha256: str
    slot_name: str

    @property
    def valid_magic(self) -> bool:
        return self.magic == BUNDLE_MAGIC

    @property
    def image_start_lba(self) -> int:
        return self.image_offset // self.block_size if self.block_size else 0

    @property
    def manifest_blocks(self) -> int:
        if not self.block_size:
            return 0
        return ((self.manifest_bytes + self.block_size - 1) // self.block_size)

    @property
    def image_blocks(self) -> int:
        return self.image_padded // self.block_size if self.block_size else 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "magic": self.magic.decode("ascii", errors="replace"),
            "block_size": self.block_size,
            "manifest_bytes": self.manifest_bytes,
            "image_offset": self.image_offset,
            "image_start_lba": self.image_start_lba,
            "image_bytes": self.image_bytes,
            "image_padded": self.image_padded,
            "image_blocks": self.image_blocks,
            "target_address": self.target_address,
            "reserved_bytes": self.reserved_bytes,
            "crc32": f"0x{self.crc32:08X}",
            "sha256": self.sha256,
            "slot_name": self.slot_name,
            "valid_magic": self.valid_magic,
        }



def compute_auto_control_checksum(block: AutoControlBlock) -> int:
    """Compute the expected checksum for an auto-recovery control block."""
    words = [
        int.from_bytes(block.magic[:4], "little", signed=False),
        int.from_bytes(block.magic[4:8], "little", signed=False),
        block.reserved & 0xFFFFFFFF,
        block.flags & 0xFFFFFFFF,
        block.primary_lba & 0xFFFFFFFF,
        block.fallback_lba & 0xFFFFFFFF,
        block.attempt_limit & 0xFFFFFFFF,
        block.attempt_count & 0xFFFFFFFF,
        block.last_result & 0xFFFFFFFF,
        block.last_error_code & 0xFFFFFFFF,
        block.last_error_detail & 0xFFFFFFFF,
        block.last_source_lba & 0xFFFFFFFF,
        block.last_bundle_crc32 & 0xFFFFFFFF,
        block.aux0 & 0xFFFFFFFF,
        block.aux1 & 0xFFFFFFFF,
    ]
    checksum = 0
    for word in words:
        checksum = (checksum + word) & 0xFFFFFFFF
    return checksum


@dataclass(slots=True)
class AutoControlBlock:
    magic: bytes
    reserved: int
    flags: int
    primary_lba: int
    fallback_lba: int
    attempt_limit: int
    attempt_count: int
    last_result: int
    last_error_code: int
    last_error_detail: int
    last_source_lba: int
    last_bundle_crc32: int
    aux0: int
    aux1: int
    checksum: int
    lba: int = AUTO_CONTROL_LBA

    @property
    def valid_magic(self) -> bool:
        return self.magic == AUTO_MAGIC

    @property
    def armed(self) -> bool:
        return bool(self.flags & AUTO_FLAG_ARMED)

    @property
    def clear_on_success(self) -> bool:
        return bool(self.flags & AUTO_FLAG_CLEAR_ON_SUCCESS)

    @property
    def allow_fallback(self) -> bool:
        return bool(self.flags & AUTO_FLAG_ALLOW_FALLBACK) and self.fallback_lba != 0

    @property
    def fallback_on_fail(self) -> bool:
        return bool(self.flags & AUTO_FLAG_FALLBACK_ON_FAIL) and self.allow_fallback

    @property
    def checksum_expected(self) -> int:
        return compute_auto_control_checksum(self)

    @property
    def checksum_ok(self) -> bool:
        return self.checksum == self.checksum_expected

    @property
    def valid(self) -> bool:
        return self.valid_magic and self.checksum_ok

    @property
    def last_result_name(self) -> str:
        return AUTO_RESULT_LABELS.get(self.last_result, f"unknown-{self.last_result}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "lba": self.lba,
            "magic": self.magic.decode("ascii", errors="replace"),
            "flags": self.flags,
            "armed": self.armed,
            "clear_on_success": self.clear_on_success,
            "allow_fallback": self.allow_fallback,
            "fallback_on_fail": self.fallback_on_fail,
            "primary_lba": self.primary_lba,
            "fallback_lba": self.fallback_lba,
            "attempt_limit": self.attempt_limit,
            "attempt_count": self.attempt_count,
            "last_result": self.last_result,
            "last_result_name": self.last_result_name,
            "last_error_code": self.last_error_code,
            "last_error_detail": self.last_error_detail,
            "last_source_lba": self.last_source_lba,
            "last_bundle_crc32": f"0x{self.last_bundle_crc32:08X}",
            "aux0": self.aux0,
            "aux1": self.aux1,
            "checksum": f"0x{self.checksum:08X}",
            "checksum_expected": f"0x{self.checksum_expected:08X}",
            "checksum_ok": self.checksum_ok,
            "valid": self.valid,
        }



@dataclass(slots=True)
class ResolvedBitstream:
    spec: str
    bitstream: Path
    project: str | None
    built: bool

    @property
    def label(self) -> str:
        if self.project:
            return f"project `{self.project}`"
        return str(self.bitstream)
