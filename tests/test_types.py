"""Tests for return type contracts and API discoverability."""

from dataclasses import fields

from icepi.flash_service import ServiceStats, UploadResult


def test_service_stats_fields():
    """ServiceStats has exactly these four fields."""
    names = {f.name for f in fields(ServiceStats)}
    assert names == {"command_count", "erase_count", "program_count", "error_count"}


def test_service_stats_as_dict():
    stats = ServiceStats(command_count=10, erase_count=2, program_count=5, error_count=0)
    d = stats.as_dict()
    assert d == {
        "command_count": 10,
        "erase_count": 2,
        "program_count": 5,
        "error_count": 0,
    }


def test_upload_result_fields():
    """UploadResult has the expected fields."""
    names = {f.name for f in fields(UploadResult)}
    assert names == {
        "base_address",
        "bytes",
        "padded_bytes",
        "erase_size",
        "chunk_size",
    }


def test_upload_result_construction():
    r = UploadResult(
        base_address=0,
        bytes=298240,
        padded_bytes=298240,
        erase_size=65536,
        chunk_size=16,
    )
    assert r.bytes == 298240


def test_all_exports_exist():
    """Every module defines __all__."""
    import icepi.build
    import icepi.bundle
    import icepi.flash_service
    import icepi.layout
    import icepi.models
    import icepi.sd
    import icepi.tools

    for mod in (
        icepi.models,
        icepi.tools,
        icepi.layout,
        icepi.bundle,
        icepi.build,
        icepi.flash_service,
        icepi.sd,
    ):
        assert hasattr(mod, "__all__"), f"{mod.__name__} missing __all__"
        for name in mod.__all__:
            assert hasattr(mod, name), f"{mod.__name__}.__all__ lists {name!r} but it does not exist"
