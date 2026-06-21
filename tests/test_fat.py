"""Tests for icepi.sd FAT32 filesystem operations (pure mock, no hardware)."""

import struct

from icepi.sd import (
    FatDirEntry,
    FatFilesystem,
    FatVolume,
    SdPartitionEntry,
)


class FakeService:
    """Mock FlashService that serves blocks from a dict."""

    def __init__(self, blocks: dict[int, bytes] | None = None):
        self.blocks: dict[int, bytes] = blocks or {}

    def sd_read(self, lba: int, *, offset: int = 0, length: int = 512) -> bytes:
        block = self.blocks.get(lba, b"\x00" * 512)
        return block[offset : offset + length]


def _make_fat32_volume(
    *,
    partition_first_lba: int = 2048,
    sectors_per_cluster: int = 8,
    reserved_sectors: int = 32,
    fat_count: int = 2,
    sectors_per_fat: int = 128,
    total_sectors: int = 100000,
    root_cluster: int = 2,
) -> FatVolume:
    fat_begin = partition_first_lba + reserved_sectors
    data_begin = fat_begin + (fat_count * sectors_per_fat)
    data_sectors = total_sectors - (reserved_sectors + fat_count * sectors_per_fat)
    cluster_count = data_sectors // sectors_per_cluster
    return FatVolume(
        partition=SdPartitionEntry(0, 0x00, 0x0C, partition_first_lba, total_sectors),
        bytes_per_sector=512,
        sectors_per_cluster=sectors_per_cluster,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        sectors_per_fat=sectors_per_fat,
        total_sectors=total_sectors,
        root_cluster=root_cluster,
        volume_label="TEST",
        fs_type="FAT32",
        fat_begin_lba=fat_begin,
        data_begin_lba=data_begin,
        cluster_count=cluster_count,
    )


def _build_fat_entry(cluster: int, next_cluster: int) -> tuple[int, int, bytes]:
    """Return (sector_lba_offset, byte_offset, 4-byte LE entry) for a FAT entry."""
    fat_offset = cluster * 4
    sector_offset = fat_offset // 512
    byte_offset = fat_offset % 512
    return sector_offset, byte_offset, struct.pack("<I", next_cluster & 0x0FFFFFFF)


def _build_dir_entry(name: str, first_cluster: int, size: int, attr: int = 0x20) -> bytes:
    """Build a minimal 32-byte FAT directory entry."""
    entry = bytearray(32)
    stem = name.split(".")[0].upper().ljust(8)[:8]
    ext = (name.split(".", 1)[1].upper().ljust(3)[:3] if "." in name else "   ")
    entry[0:8] = stem.encode("ascii")
    entry[8:11] = ext.encode("ascii")
    entry[11] = attr
    hi = (first_cluster >> 16) & 0xFFFF
    lo = first_cluster & 0xFFFF
    struct.pack_into("<H", entry, 20, hi)
    struct.pack_into("<H", entry, 26, lo)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def test_fat_volume_properties():
    vol = _make_fat32_volume(sectors_per_cluster=8)
    assert vol.cluster_size == 512 * 8
    assert vol.total_bytes == 100000 * 512


def test_fat_cluster_to_lba():
    vol = _make_fat32_volume()
    fs = FatFilesystem(FakeService(), vol)
    # Cluster 2 is the first data cluster
    assert fs.cluster_to_lba(2) == vol.data_begin_lba


def test_fat_cluster_chain_single():
    vol = _make_fat32_volume()
    # Set up FAT: cluster 2 -> EOC
    fat_sector = bytearray(512)
    _, off, data = _build_fat_entry(2, 0x0FFFFFF8)
    fat_sector[off : off + 4] = data
    blocks = {vol.fat_begin_lba: bytes(fat_sector)}
    fs = FatFilesystem(FakeService(blocks), vol)
    chain = fs.cluster_chain(2)
    assert chain == [2]


def test_fat_cluster_chain_multi():
    vol = _make_fat32_volume()
    fat_sector = bytearray(512)
    for cluster, next_c in [(2, 3), (3, 4), (4, 0x0FFFFFF8)]:
        _, off, data = _build_fat_entry(cluster, next_c)
        fat_sector[off : off + 4] = data
    blocks = {vol.fat_begin_lba: bytes(fat_sector)}
    fs = FatFilesystem(FakeService(blocks), vol)
    chain = fs.cluster_chain(2)
    assert chain == [2, 3, 4]


def test_fat_cluster_chain_loop_detected():
    vol = _make_fat32_volume()
    fat_sector = bytearray(512)
    for cluster, next_c in [(2, 3), (3, 2)]:
        _, off, data = _build_fat_entry(cluster, next_c)
        fat_sector[off : off + 4] = data
    blocks = {vol.fat_begin_lba: bytes(fat_sector)}
    fs = FatFilesystem(FakeService(blocks), vol)
    try:
        fs.cluster_chain(2)
        assert False, "should have raised"
    except ValueError as exc:
        assert "loop" in str(exc)


def test_fat_list_directory():
    vol = _make_fat32_volume()
    # FAT: cluster 2 -> EOC
    fat_sector = bytearray(512)
    _, off, data = _build_fat_entry(2, 0x0FFFFFF8)
    fat_sector[off : off + 4] = data

    # Build root directory in cluster 2 with one file entry
    dir_data = bytearray(vol.cluster_size)
    dir_data[0:32] = _build_dir_entry("test.txt", 3, 42)
    dir_data[32] = 0x00  # end marker

    blocks = {vol.fat_begin_lba: bytes(fat_sector)}
    # Cluster 2 spans sectors data_begin_lba .. data_begin_lba + spc - 1
    for i in range(vol.sectors_per_cluster):
        start = i * 512
        blocks[vol.data_begin_lba + i] = bytes(dir_data[start : start + 512])

    fs = FatFilesystem(FakeService(blocks), vol)
    entries = fs.list_directory()
    assert len(entries) == 1
    assert entries[0].name == "TEST.TXT"
    assert entries[0].size == 42
    assert entries[0].first_cluster == 3
    assert entries[0].kind == "file"


def test_fat_resolve_root():
    vol = _make_fat32_volume()
    fs = FatFilesystem(FakeService(), vol)
    assert fs.resolve("/") is None
    assert fs.resolve("") is None


def test_fat_read_file():
    vol = _make_fat32_volume()
    # FAT: cluster 2 -> EOC (root dir), cluster 3 -> EOC (file data)
    fat_sector = bytearray(512)
    for cluster, next_c in [(2, 0x0FFFFFF8), (3, 0x0FFFFFF8)]:
        _, off, data = _build_fat_entry(cluster, next_c)
        fat_sector[off : off + 4] = data

    file_content = b"Hello RIME!"
    file_size = len(file_content)

    dir_data = bytearray(vol.cluster_size)
    dir_data[0:32] = _build_dir_entry("hello.txt", 3, file_size)
    dir_data[32] = 0x00

    file_cluster = bytearray(vol.cluster_size)
    file_cluster[: len(file_content)] = file_content

    blocks = {vol.fat_begin_lba: bytes(fat_sector)}
    for i in range(vol.sectors_per_cluster):
        blocks[vol.data_begin_lba + i] = bytes(dir_data[i * 512 : (i + 1) * 512])
        file_lba = vol.data_begin_lba + vol.sectors_per_cluster + i
        blocks[file_lba] = bytes(file_cluster[i * 512 : (i + 1) * 512])

    fs = FatFilesystem(FakeService(blocks), vol)
    data = fs.read_file("hello.txt")
    assert data == file_content


def test_fat_dir_entry_kinds():
    e_file = FatDirEntry("a.txt", "A.TXT", 0x20, 3, 100)
    assert e_file.kind == "file"
    assert not e_file.is_dir

    e_dir = FatDirEntry("subdir", "SUBDIR", 0x10, 4, 0)
    assert e_dir.kind == "dir"
    assert e_dir.is_dir

    e_label = FatDirEntry("VOLUME", "VOLUME", 0x08, 0, 0)
    assert e_label.kind == "label"
    assert e_label.is_volume_label
