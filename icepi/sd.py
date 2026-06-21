"""SD card operations: partitions, FAT32, bundles, staging, auto-recovery."""

from __future__ import annotations

import binascii
import struct
from dataclasses import dataclass
from time import sleep
from typing import Any

__all__ = [
    "SdPartitionEntry",
    "FatVolume",
    "FatDirEntry",
    "FatFilesystem",
    "parse_sd_partitions",
    "render_sd_layout_lines",
    "sd_gaps_from_partitions",
    "find_sd_staging_lba",
    "read_sd_bytes",
    "load_fat_volume",
    "render_fat_volume_lines",
    "render_fat_directory_lines",
    "build_auto_control_block",
    "encode_auto_control_block",
    "parse_auto_control_block",
    "validate_auto_control_block",
    "render_auto_control_lines",
    "ensure_sd_initialized",
    "write_sd_block_with_recovery",
    "read_auto_control_block",
    "write_auto_control_block",
    "stage_bundle_to_sd",
]

from icepi.flash_service import (
    ERR_SD,
    FlashService,
    FlashServiceError,
    FlashServiceRemoteError,
    FlashServiceTimeout,
    FlashServiceVerifyError,
    SdInfo,
    auto_progress_text,
)
from icepi.models import (
    AUTO_CONTROL_BYTES,
    AUTO_CONTROL_LBA,
    AUTO_FLAG_ALLOW_FALLBACK,
    AUTO_FLAG_ARMED,
    AUTO_FLAG_CLEAR_ON_SUCCESS,
    AUTO_FLAG_FALLBACK_ON_FAIL,
    AUTO_MAGIC,
    AUTO_RESULT_NONE,
    AutoControlBlock,
    compute_auto_control_checksum,
)
from icepi.tools import make_progress_renderer


@dataclass(slots=True)
class SdPartitionEntry:
    index: int
    status: int
    type_code: int
    first_lba: int
    sectors: int

    @property
    def present(self) -> bool:
        return self.type_code != 0 and self.sectors > 0

    @property
    def bootable(self) -> bool:
        return self.status == 0x80

    @property
    def last_lba(self) -> int:
        return self.first_lba + self.sectors - 1 if self.sectors else self.first_lba

    @property
    def bytes(self) -> int:
        return self.sectors * 512

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "status": self.status,
            "type_code": self.type_code,
            "first_lba": self.first_lba,
            "sectors": self.sectors,
            "last_lba": self.last_lba,
            "bytes": self.bytes,
            "present": self.present,
            "bootable": self.bootable,
        }


def parse_sd_partitions(block0: bytes) -> list[SdPartitionEntry]:
    """Parse the four MBR partition entries from the first 512-byte SD block.

    Raises ``ValueError`` if the card uses GPT partitioning (protective MBR
    with type 0xEE), since raw staging addresses cannot be safely computed
    from the protective MBR alone.
    """
    if len(block0) < 512:
        raise ValueError("SD layout parsing needs the full first 512-byte block")
    if block0[510:512] != b"\x55\xAA":
        raise ValueError("SD block 0 does not contain an MBR signature")
    if block0[450] == 0xEE:
        raise ValueError(
            "SD card uses GPT partitioning (protective MBR type 0xEE). "
            "RIME requires MBR partitioning for raw staging. "
            "Re-partition with MBR or use a different card."
        )
    partitions: list[SdPartitionEntry] = []
    for index in range(4):
        offset = 446 + (index * 16)
        entry = block0[offset : offset + 16]
        partitions.append(
            SdPartitionEntry(
                index=index,
                status=entry[0],
                type_code=entry[4],
                first_lba=struct.unpack_from("<I", entry, 8)[0],
                sectors=struct.unpack_from("<I", entry, 12)[0],
            )
        )
    return [p for p in partitions if p.present]


def render_sd_layout_lines(partitions: list[SdPartitionEntry]) -> list[str]:
    """Format partition table information as human-readable lines."""
    lines = ["SD layout:", "MBR signature: 0x55AA"]
    present = [entry for entry in partitions if entry.present]
    if not present:
        lines.append("Partitions: none")
        return lines
    for entry in present:
        flags = []
        if entry.bootable:
            flags.append("bootable")
        suffix = f" [{' '.join(flags)}]" if flags else ""
        lines.append(
            f"Partition {entry.index}: type=0x{entry.type_code:02X} "
            f"LBA {entry.first_lba}-{entry.last_lba} "
            f"({entry.sectors} blocks / {entry.bytes} bytes){suffix}"
        )
    first_lba = min(entry.first_lba for entry in present)
    if first_lba > 1:
        gap_first = 1
        gap_last = first_lba - 1
        gap_blocks = gap_last - gap_first + 1
        aligned = ((gap_first + 2047) // 2048) * 2048
        lines.append(
            f"Pre-partition raw gap: LBA {gap_first}-{gap_last} "
            f"({gap_blocks} blocks / {gap_blocks * 512} bytes)"
        )
        if aligned <= gap_last:
            lines.append(f"Suggested aligned raw staging LBA: {aligned}")
    return lines


def sd_gaps_from_partitions(partitions: list[SdPartitionEntry]) -> list[tuple[int, int]]:
    """Return ``(start_lba, end_lba)`` pairs for raw gaps between partitions."""
    present = sorted((entry for entry in partitions if entry.present), key=lambda entry: entry.first_lba)
    if not present:
        return []
    gaps: list[tuple[int, int]] = []
    if present[0].first_lba > 1:
        gaps.append((1, present[0].first_lba - 1))
    for left, right in zip(present, present[1:]):
        gap_start = left.last_lba + 1
        gap_end = right.first_lba - 1
        if gap_end >= gap_start:
            gaps.append((gap_start, gap_end))
    return gaps


def find_sd_staging_lba(
    partitions: list[SdPartitionEntry],
    *,
    required_blocks: int,
    lba: int | None = None,
    align_blocks: int = 2048,
    reserved_ranges: list[tuple[int, int]] | None = None,
) -> int:
    """Find a safe raw-SD LBA for staging a bundle.

    Searches gaps between partitions, avoids reserved ranges, and
    prefers aligned addresses.
    """
    if required_blocks <= 0:
        raise ValueError("required block count must be positive")
    reserved = list(reserved_ranges or [])
    if not any(s <= AUTO_CONTROL_LBA <= e for s, e in reserved):
        reserved.append((AUTO_CONTROL_LBA, AUTO_CONTROL_LBA))

    def overlap_end(candidate_start: int, candidate_end: int) -> int | None:
        for reserved_start, reserved_end in reserved:
            if candidate_start <= reserved_end and reserved_start <= candidate_end:
                return reserved_end
        return None

    def fits(candidate_start: int, candidate_end: int) -> bool:
        return overlap_end(candidate_start, candidate_end) is None

    def find_candidate(gap_start: int, gap_end: int, *, aligned: bool) -> int | None:
        candidate = gap_start
        if aligned:
            candidate = ((candidate + align_blocks - 1) // align_blocks) * align_blocks
        while candidate + required_blocks - 1 <= gap_end:
            candidate_end = candidate + required_blocks - 1
            overlap = overlap_end(candidate, candidate_end)
            if overlap is None:
                return candidate
            candidate = overlap + 1
            if aligned:
                candidate = ((candidate + align_blocks - 1) // align_blocks) * align_blocks
        return None

    gaps = sd_gaps_from_partitions(partitions)
    if lba is not None:
        start = lba
        end = lba + required_blocks - 1
        if start < 0:
            raise ValueError("staging LBA must be non-negative")
        if gaps:
            for gap_start, gap_end in gaps:
                if start >= gap_start and end <= gap_end and fits(start, end):
                    return start
            raise ValueError(
                f"requested LBA range {start}-{end} does not fit in any raw SD gap; use `sd layout` to inspect safe staging regions"
            )
        # No partition table: the whole card is raw space. Honor the explicit
        # LBA as long as it clears reserved regions (e.g. the auto-control block).
        if not fits(start, end):
            raise ValueError(
                f"requested LBA range {start}-{end} overlaps a reserved SD region (e.g. the auto-control block at LBA {AUTO_CONTROL_LBA})"
            )
        return start
    for gap_start, gap_end in gaps:
        candidate = find_candidate(gap_start, gap_end, aligned=True)
        if candidate is not None:
            return candidate
        candidate = find_candidate(gap_start, gap_end, aligned=False)
        if candidate is not None:
            return candidate
    raise ValueError(
        f"no raw SD gap is large enough for {required_blocks} blocks; use `sd layout` to inspect media geometry"
    )



def read_sd_bytes(service: FlashService, *, lba: int, offset: int = 0, length: int) -> bytes:
    """Read *length* bytes from the SD card spanning blocks as needed.  Returns ``bytes``."""
    if lba < 0:
        raise ValueError("SD LBA must be non-negative")
    if offset < 0 or length < 0:
        raise ValueError("SD offset and length must be non-negative")
    if length == 0:
        return b""
    block = lba
    intra = offset
    data = bytearray()
    remaining = length
    while remaining:
        if intra >= 512:
            block += intra // 512
            intra %= 512
        take = min(remaining, 512 - intra)
        data.extend(service.sd_read(block, offset=intra, length=take))
        remaining -= take
        block += 1
        intra = 0
    return bytes(data)



FAT_PARTITION_TYPES = {0x0B, 0x0C, 0x0E}
FAT_EOC = 0x0FFFFFF8


@dataclass(slots=True)
class FatVolume:
    partition: SdPartitionEntry
    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    fat_count: int
    sectors_per_fat: int
    total_sectors: int
    root_cluster: int
    volume_label: str
    fs_type: str
    fat_begin_lba: int
    data_begin_lba: int
    cluster_count: int

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def total_bytes(self) -> int:
        return self.total_sectors * self.bytes_per_sector

    def as_dict(self) -> dict[str, Any]:
        return {
            "partition": self.partition.as_dict(),
            "bytes_per_sector": self.bytes_per_sector,
            "sectors_per_cluster": self.sectors_per_cluster,
            "reserved_sectors": self.reserved_sectors,
            "fat_count": self.fat_count,
            "sectors_per_fat": self.sectors_per_fat,
            "total_sectors": self.total_sectors,
            "root_cluster": self.root_cluster,
            "volume_label": self.volume_label,
            "fs_type": self.fs_type,
            "fat_begin_lba": self.fat_begin_lba,
            "data_begin_lba": self.data_begin_lba,
            "cluster_count": self.cluster_count,
            "cluster_size": self.cluster_size,
            "total_bytes": self.total_bytes,
        }


@dataclass(slots=True)
class FatDirEntry:
    name: str
    short_name: str
    attr: int
    first_cluster: int
    size: int

    @property
    def is_dir(self) -> bool:
        return bool(self.attr & 0x10)

    @property
    def is_volume_label(self) -> bool:
        return bool(self.attr & 0x08)

    @property
    def kind(self) -> str:
        if self.is_volume_label:
            return "label"
        if self.is_dir:
            return "dir"
        return "file"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "short_name": self.short_name,
            "attr": self.attr,
            "first_cluster": self.first_cluster,
            "size": self.size,
            "kind": self.kind,
        }


def _clean_ascii_label(data: bytes) -> str:
    text = data.decode("ascii", errors="ignore").rstrip()
    return text or "<unnamed>"


def _decode_lfn_part(entry: bytes) -> str:
    text = bytearray()
    fields = (entry[1:11], entry[14:26], entry[28:32])
    for field in fields:
        for index in range(0, len(field), 2):
            code_unit = int.from_bytes(field[index : index + 2], "little", signed=False)
            if code_unit == 0x0000:
                return text.decode("utf-16le", errors="ignore")
            if code_unit == 0xFFFF:
                continue
            text.extend(field[index : index + 2])
    return text.decode("utf-16le", errors="ignore")


def _short_name(entry: bytes) -> str:
    stem = entry[0:8].decode("ascii", errors="ignore").rstrip()
    ext = entry[8:11].decode("ascii", errors="ignore").rstrip()
    if ext:
        return f"{stem}.{ext}"
    return stem


def _pick_fat_partition(partitions: list[SdPartitionEntry], *, partition_index: int | None) -> SdPartitionEntry:
    if partition_index is not None:
        if not 1 <= partition_index <= 4:
            raise ValueError("partition index must be between 1 and 4")
        chosen = partitions[partition_index - 1]
        if not chosen.present:
            raise ValueError(f"partition {partition_index} is not present")
        if chosen.type_code not in FAT_PARTITION_TYPES:
            raise ValueError(
                f"partition {partition_index} type 0x{chosen.type_code:02X} is not a supported FAT volume"
            )
        return chosen
    for entry in partitions:
        if entry.present and entry.type_code in FAT_PARTITION_TYPES:
            return entry
    raise ValueError("no supported FAT partition found on the current SD card")


def load_fat_volume(service: FlashService, *, partition_index: int | None = None) -> FatVolume:
    """Read and parse a FAT32 volume from the SD card."""
    block0 = read_sd_bytes(service, lba=0, length=512)
    partitions = parse_sd_partitions(block0)
    partition = _pick_fat_partition(partitions, partition_index=partition_index)
    boot = read_sd_bytes(service, lba=partition.first_lba, length=512)
    if boot[510:512] != b"\x55\xAA":
        raise ValueError(f"partition {partition.index + 1} does not have a valid FAT boot signature")
    bytes_per_sector = struct.unpack_from("<H", boot, 11)[0]
    sectors_per_cluster = boot[13]
    reserved_sectors = struct.unpack_from("<H", boot, 14)[0]
    fat_count = boot[16]
    root_entry_count = struct.unpack_from("<H", boot, 17)[0]
    total_sectors_16 = struct.unpack_from("<H", boot, 19)[0]
    sectors_per_fat_16 = struct.unpack_from("<H", boot, 22)[0]
    total_sectors_32 = struct.unpack_from("<I", boot, 32)[0]
    sectors_per_fat_32 = struct.unpack_from("<I", boot, 36)[0]
    root_cluster = struct.unpack_from("<I", boot, 44)[0]
    total_sectors = total_sectors_16 or total_sectors_32
    sectors_per_fat = sectors_per_fat_16 or sectors_per_fat_32
    if bytes_per_sector != 512:
        raise ValueError(f"unsupported FAT bytes/sector {bytes_per_sector}; only 512-byte sectors are supported")
    if sectors_per_cluster == 0:
        raise ValueError("invalid FAT volume: sectors/cluster is zero")
    if root_entry_count != 0 or sectors_per_fat_32 == 0:
        raise ValueError("only FAT32 volumes are supported right now")
    fat_begin_lba = partition.first_lba + reserved_sectors
    data_begin_lba = fat_begin_lba + (fat_count * sectors_per_fat)
    data_sectors = total_sectors - (reserved_sectors + (fat_count * sectors_per_fat))
    cluster_count = data_sectors // sectors_per_cluster
    return FatVolume(
        partition=partition,
        bytes_per_sector=bytes_per_sector,
        sectors_per_cluster=sectors_per_cluster,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        sectors_per_fat=sectors_per_fat,
        total_sectors=total_sectors,
        root_cluster=root_cluster,
        volume_label=_clean_ascii_label(boot[71:82]),
        fs_type=_clean_ascii_label(boot[82:90]),
        fat_begin_lba=fat_begin_lba,
        data_begin_lba=data_begin_lba,
        cluster_count=cluster_count,
    )


class FatFilesystem:
    """Read-only FAT32 filesystem accessor backed by board-side SD reads."""

    CACHE_LIMIT = 256

    def __init__(self, service: FlashService, volume: FatVolume) -> None:
        self.service = service
        self.volume = volume
        self._sector_cache: dict[int, bytes] = {}

    def read_sector(self, lba: int) -> bytes:
        if lba not in self._sector_cache:
            if len(self._sector_cache) >= self.CACHE_LIMIT:
                oldest = next(iter(self._sector_cache))
                del self._sector_cache[oldest]
            self._sector_cache[lba] = read_sd_bytes(self.service, lba=lba, length=512)
        return self._sector_cache[lba]

    def read_sectors(self, start_lba: int, count: int) -> bytes:
        if count < 0:
            raise ValueError("sector count must be non-negative")
        return b"".join(self.read_sector(start_lba + offset) for offset in range(count))

    def cluster_to_lba(self, cluster: int) -> int:
        if cluster < 2:
            raise ValueError(f"invalid cluster {cluster}")
        return self.volume.data_begin_lba + ((cluster - 2) * self.volume.sectors_per_cluster)

    def read_fat_entry(self, cluster: int) -> int:
        fat_offset = cluster * 4
        sector_lba = self.volume.fat_begin_lba + (fat_offset // 512)
        sector_offset = fat_offset % 512
        entry = self.read_sector(sector_lba)[sector_offset : sector_offset + 4]
        if len(entry) != 4:
            raise ValueError(f"incomplete FAT entry for cluster {cluster}")
        return int(struct.unpack_from("<I", entry, 0)[0]) & 0x0FFFFFFF

    def cluster_chain(self, start_cluster: int, *, limit: int = 65536) -> list[int]:
        """Follow a FAT cluster chain from *start_cluster* to end-of-chain."""
        if start_cluster < 2:
            return []
        chain: list[int] = []
        seen: set[int] = set()
        cluster = start_cluster
        while True:
            if cluster in seen:
                raise ValueError(f"FAT cluster loop detected at cluster {cluster}")
            seen.add(cluster)
            chain.append(cluster)
            if len(chain) > limit:
                raise ValueError("FAT cluster chain exceeded the safety limit")
            next_cluster = self.read_fat_entry(cluster)
            if next_cluster >= FAT_EOC:
                return chain
            if next_cluster < 2:
                raise ValueError(f"FAT chain for cluster {start_cluster} terminated early at {next_cluster}")
            cluster = next_cluster

    def read_cluster(self, cluster: int) -> bytes:
        return self.read_sectors(self.cluster_to_lba(cluster), self.volume.sectors_per_cluster)

    def read_chain(self, start_cluster: int) -> bytes:
        data = bytearray()
        for cluster in self.cluster_chain(start_cluster):
            data.extend(self.read_cluster(cluster))
        return bytes(data)

    def list_directory(self, cluster: int | None = None) -> list[FatDirEntry]:
        cluster = self.volume.root_cluster if cluster is None else cluster
        raw = self.read_chain(cluster)
        entries: list[FatDirEntry] = []
        lfn_parts: list[str] = []
        for offset in range(0, len(raw), 32):
            entry = raw[offset : offset + 32]
            if len(entry) < 32:
                break
            marker = entry[0]
            attr = entry[11]
            if marker == 0x00:
                break
            if marker == 0xE5:
                lfn_parts.clear()
                continue
            if attr == 0x0F:
                lfn_parts.append(_decode_lfn_part(entry))
                continue
            short = _short_name(entry)
            name = "".join(reversed(lfn_parts)).strip() or short
            lfn_parts.clear()
            first_cluster = ((struct.unpack_from("<H", entry, 20)[0] << 16) | struct.unpack_from("<H", entry, 26)[0])
            item = FatDirEntry(
                name=name,
                short_name=short,
                attr=attr,
                first_cluster=first_cluster,
                size=struct.unpack_from("<I", entry, 28)[0],
            )
            if item.is_volume_label:
                continue
            entries.append(item)
        return entries

    def resolve(self, path: str) -> FatDirEntry | None:
        """Resolve a ``/``-separated path to a directory entry, or *None* for root."""
        text = path.replace("\\", "/").strip()
        if text in {"", "/"}:
            return None
        parts = [part for part in text.split("/") if part and part != "."]
        current_cluster = self.volume.root_cluster
        current_entry: FatDirEntry | None = None
        for part in parts:
            entries = self.list_directory(current_cluster)
            wanted = part.casefold()
            current_entry = next(
                (
                    entry
                    for entry in entries
                    if entry.name.casefold() == wanted or entry.short_name.casefold() == wanted
                ),
                None,
            )
            if current_entry is None:
                raise FileNotFoundError(path)
            if part != parts[-1]:
                if not current_entry.is_dir:
                    raise ValueError(f"`{part}` is not a directory")
                current_cluster = current_entry.first_cluster or self.volume.root_cluster
        return current_entry

    def read_file(self, path: str) -> bytes:
        entry = self.resolve(path)
        if entry is None:
            raise ValueError("path refers to the root directory, not a file")
        if entry.is_dir:
            raise ValueError(f"`{path}` is a directory")
        if entry.first_cluster < 2 or entry.size == 0:
            return b""
        return self.read_chain(entry.first_cluster)[: entry.size]


def render_fat_volume_lines(volume: FatVolume) -> list[str]:
    """Format FAT32 volume geometry as human-readable lines."""
    return [
        f"Filesystem: {volume.fs_type}",
        f"Volume label: {volume.volume_label}",
        f"Partition: {volume.partition.index + 1} (type=0x{volume.partition.type_code:02X})",
        f"Partition LBA: {volume.partition.first_lba}-{volume.partition.last_lba}",
        f"Total sectors: {volume.total_sectors}",
        f"Total bytes: {volume.total_bytes}",
        f"Bytes/sector: {volume.bytes_per_sector}",
        f"Sectors/cluster: {volume.sectors_per_cluster}",
        f"Cluster size: {volume.cluster_size}",
        f"Reserved sectors: {volume.reserved_sectors}",
        f"FAT copies: {volume.fat_count}",
        f"Sectors/FAT: {volume.sectors_per_fat}",
        f"Root cluster: {volume.root_cluster}",
        f"Data start LBA: {volume.data_begin_lba}",
        f"Cluster count: {volume.cluster_count}",
    ]


def render_fat_directory_lines(path: str, entries: list[FatDirEntry]) -> list[str]:
    """Format a directory listing as human-readable lines."""
    header = path if path else "/"
    lines = [f"Directory: {header}"]
    if not entries:
        lines.append("<empty>")
        return lines
    for entry in entries:
        size_text = "-" if entry.is_dir else str(entry.size)
        lines.append(
            f"{entry.kind:>4}  cluster={entry.first_cluster:<8d} size={size_text:<10} {entry.name}"
        )
    return lines



def build_auto_control_block(
    *,
    primary_lba: int = 0,
    fallback_lba: int = 0,
    attempt_limit: int = 3,
    attempt_count: int = 0,
    last_result: int = AUTO_RESULT_NONE,
    last_error_code: int = 0,
    last_error_detail: int = 0,
    last_source_lba: int = 0,
    last_bundle_crc32: int = 0,
    armed: bool = False,
    clear_on_success: bool = True,
    fallback_on_fail: bool = True,
    lba: int = AUTO_CONTROL_LBA,
) -> AutoControlBlock:
    """Construct an :class:`AutoControlBlock` with a valid checksum.

    Set *armed* to ``True`` and *primary_lba* to the bundle staging LBA
    to enable startup auto-recovery on the next boot.
    """
    flags = 0
    if armed:
        flags |= AUTO_FLAG_ARMED
    if clear_on_success:
        flags |= AUTO_FLAG_CLEAR_ON_SUCCESS
    if fallback_lba:
        flags |= AUTO_FLAG_ALLOW_FALLBACK
        if fallback_on_fail:
            flags |= AUTO_FLAG_FALLBACK_ON_FAIL
    block = AutoControlBlock(
        magic=AUTO_MAGIC,
        reserved=0,
        flags=flags,
        primary_lba=primary_lba,
        fallback_lba=fallback_lba,
        attempt_limit=attempt_limit,
        attempt_count=attempt_count,
        last_result=last_result,
        last_error_code=last_error_code,
        last_error_detail=last_error_detail,
        last_source_lba=last_source_lba,
        last_bundle_crc32=last_bundle_crc32,
        aux0=0,
        aux1=0,
        checksum=0,
        lba=lba,
    )
    block.checksum = compute_auto_control_checksum(block)
    return block


def encode_auto_control_block(block: AutoControlBlock) -> bytes:
    """Serialize an :class:`AutoControlBlock` into a 512-byte SD block."""
    encoded = bytearray(512)
    checksum = compute_auto_control_checksum(block)
    # Pack as little-endian: 8-byte magic string + 14 × 32-bit unsigned ints.
    # Total = 8 + 56 = 64 bytes, padded to 512 for a full SD block.
    struct.pack_into(
        "<8s14I",
        encoded,
        0,
        block.magic,
        block.reserved,
        block.flags,
        block.primary_lba,
        block.fallback_lba,
        block.attempt_limit,
        block.attempt_count,
        block.last_result,
        block.last_error_code,
        block.last_error_detail,
        block.last_source_lba,
        block.last_bundle_crc32,
        block.aux0,
        block.aux1,
        checksum,
    )
    return bytes(encoded)


def parse_auto_control_block(data: bytes, *, lba: int = AUTO_CONTROL_LBA) -> AutoControlBlock:
    """Decode an :class:`AutoControlBlock` from raw bytes (at least 64 bytes)."""
    if len(data) < AUTO_CONTROL_BYTES:
        raise ValueError(f"auto control block needs {AUTO_CONTROL_BYTES} bytes, got {len(data)}")
    unpacked = struct.unpack_from("<8s14I", data, 0)
    (
        magic, reserved, flags, primary_lba, fallback_lba,
        attempt_limit, attempt_count, last_result,
        last_error_code, last_error_detail, last_source_lba,
        last_bundle_crc32, aux0, aux1, checksum,
    ) = unpacked
    return AutoControlBlock(
        magic=magic, reserved=reserved, flags=flags,
        primary_lba=primary_lba, fallback_lba=fallback_lba,
        attempt_limit=attempt_limit, attempt_count=attempt_count,
        last_result=last_result, last_error_code=last_error_code,
        last_error_detail=last_error_detail, last_source_lba=last_source_lba,
        last_bundle_crc32=last_bundle_crc32, aux0=aux0, aux1=aux1,
        checksum=checksum, lba=lba,
    )


def validate_auto_control_block(block: AutoControlBlock) -> None:
    """Raise ``ValueError`` if the auto-recovery control block is invalid."""
    if not block.valid_magic:
        raise ValueError(f"unexpected auto-control magic {block.magic!r}")
    if not block.checksum_ok:
        raise ValueError(
            f"bad auto-control checksum (stored=0x{block.checksum:08X} expected=0x{block.checksum_expected:08X})"
        )


def render_auto_control_lines(block: AutoControlBlock) -> list[str]:
    """Format an auto-recovery control block as human-readable lines."""
    validity = "valid" if block.valid else "invalid"
    lines = [
        f"Auto control: {validity}",
        f"Control LBA: {block.lba}",
        f"Magic: {block.magic.decode('ascii', errors='replace')}",
        f"Flags: 0x{block.flags:08X}",
        f"Armed: {'yes' if block.armed else 'no'}",
        f"Clear on success: {'yes' if block.clear_on_success else 'no'}",
        f"Fallback enabled: {'yes' if block.allow_fallback else 'no'}",
        f"Fallback on fail: {'yes' if block.fallback_on_fail else 'no'}",
        f"Primary bundle LBA: {block.primary_lba}",
        f"Fallback bundle LBA: {block.fallback_lba}",
        f"Attempt limit: {block.attempt_limit}",
        f"Attempt count: {block.attempt_count}",
        f"Last result: {block.last_result_name} ({block.last_result})",
        f"Last error: code=0x{block.last_error_code:08X} detail=0x{block.last_error_detail:08X}",
        f"Last source LBA: {block.last_source_lba}",
        f"Last bundle CRC32: 0x{block.last_bundle_crc32:08X}",
        f"Progress: {auto_progress_text(block.aux0, block.aux1)}",
        f"Checksum: 0x{block.checksum:08X}",
        f"Expected checksum: 0x{block.checksum_expected:08X}",
    ]
    return lines



RECOVERABLE_SD_WRITE_DETAILS = {0x02, 0x0C, 0x0D, 0x0E}


def ensure_sd_initialized(service: FlashService) -> SdInfo:
    """Initialize the SD card if not already initialized."""
    info = service.sd_info()
    if not info.initialized:
        info = service.sd_init()
    return info


def write_sd_block_with_recovery(
    service: FlashService, lba: int, data: bytes, *, max_retries: int = 3,
) -> None:
    """Write a single 512-byte block to SD with exponential backoff.

    Retries up to *max_retries* times with increasing delays (0.1s, 0.3s, 0.9s)
    and SD re-initialization between attempts.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt == 0:
            ensure_sd_initialized(service)
        else:
            backoff = 0.1 * (3 ** (attempt - 1))
            sleep(min(backoff, 5.0))
            service.sd_init()
        try:
            service.sd_write512(lba, data, timeout=40.0)
            return
        except FlashServiceTimeout as exc:
            last_exc = exc
        except FlashServiceRemoteError as exc:
            last_exc = exc
            if exc.code != ERR_SD or exc.detail not in RECOVERABLE_SD_WRITE_DETAILS:
                raise
    if last_exc is None:
        raise FlashServiceError(f"unable to stage SD block {lba}")
    raise last_exc


def read_auto_control_block(service: FlashService, *, lba: int = AUTO_CONTROL_LBA) -> AutoControlBlock:
    """Read and decode the auto-recovery control block from SD."""
    return parse_auto_control_block(read_sd_bytes(service, lba=lba, length=512), lba=lba)


def write_auto_control_block(service: FlashService, block: AutoControlBlock) -> None:
    """Encode and write an auto-recovery control block to SD."""
    write_sd_block_with_recovery(service, block.lba, encode_auto_control_block(block))



def stage_bundle_to_sd(
    service: FlashService,
    *,
    bundle_bytes: bytes,
    requested_lba: int | None = None,
    no_verify: bool = False,
    verbose: bool = False,
    reserved_ranges: list[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """Write a RIME bundle into raw SD space, verify, and return ``(stage_lba, block_count)``."""
    if len(bundle_bytes) % 512 != 0:
        raise ValueError("bundle bytes must be padded to full 512-byte blocks")
    block_count = len(bundle_bytes) // 512
    if requested_lba is None:
        # Auto-placement needs the partition table to find a safe gap.
        partitions = parse_sd_partitions(read_sd_bytes(service, lba=0, length=512))
    else:
        # An explicit raw LBA does not require a partitioned card; still parse a
        # present table so gap-fit protection is kept on partitioned media.
        try:
            partitions = parse_sd_partitions(read_sd_bytes(service, lba=0, length=512))
        except ValueError:
            partitions = []
    stage_lba = find_sd_staging_lba(
        partitions,
        required_blocks=block_count,
        lba=requested_lba,
        reserved_ranges=[(AUTO_CONTROL_LBA, AUTO_CONTROL_LBA), *(reserved_ranges or [])],
    )
    write_progress = make_progress_renderer(verbose)
    verify_progress = make_progress_renderer(verbose)
    for index in range(block_count):
        block_lba = stage_lba + index
        block = bundle_bytes[index * 512 : (index + 1) * 512]
        write_progress("sd-write", index, block_count, f"LBA {block_lba}")
        write_sd_block_with_recovery(service, block_lba, block)
    write_progress("sd-write", block_count, block_count, None)
    if not no_verify:
        verify_progress("sd-vfy", 0, 1, f"LBA {stage_lba}-{stage_lba + block_count - 1}")
        expected_bundle_crc32 = binascii.crc32(bundle_bytes) & 0xFFFFFFFF
        actual_bundle_crc32 = service.sd_crc32_range(stage_lba, block_count)
        if actual_bundle_crc32 != expected_bundle_crc32:
            for index in range(block_count):
                block_lba = stage_lba + index
                block = bundle_bytes[index * 512 : (index + 1) * 512]
                verify_progress("sd-vfy", index, block_count, f"LBA {block_lba}")
                expected_crc32 = binascii.crc32(block) & 0xFFFFFFFF
                actual_crc32 = service.sd_crc32(block_lba)
                if actual_crc32 != expected_crc32:
                    read_back = read_sd_bytes(service, lba=block_lba, length=512)
                    if read_back != block:
                        raise FlashServiceVerifyError(block_lba, block[:64], read_back[:64])
                    raise FlashServiceError(
                        f"SD CRC32 mismatch at LBA {block_lba} "
                        f"(expected=0x{expected_crc32:08X} actual=0x{actual_crc32:08X})"
                    )
            raise FlashServiceError(
                f"SD bundle CRC32 mismatch across staged range "
                f"(expected=0x{expected_bundle_crc32:08X} actual=0x{actual_bundle_crc32:08X})"
            )
        verify_progress("sd-vfy", 1, 1, None)
    return stage_lba, block_count
