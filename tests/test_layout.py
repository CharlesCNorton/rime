"""Tests for icepi.layout — layout loading, image planning."""


from icepi.layout import load_layout, render_layout_lines
from icepi.tools import REPO_ROOT


def test_load_layout():
    layout = load_layout(REPO_ROOT / "config" / "icepi-layout.json")
    assert layout.flash_size == 0x01000000
    assert layout.default_slot == "boot"
    assert "boot" in layout.slots
    assert "backup" in layout.slots
    assert "staging" in layout.slots
    assert "scratch" in layout.slots
    assert layout.slots["boot"].bootable
    assert not layout.slots["backup"].bootable


def test_resolve_aliases():
    layout = load_layout(REPO_ROOT / "config" / "icepi-layout.json")
    assert layout.resolve_slot("resident").name == "boot"
    assert layout.resolve_slot("supervisor").name == "boot"
    assert layout.resolve_slot("recovery").name == "backup"
    assert layout.resolve_slot("primary").name == "boot"
    assert layout.resolve_slot("data").name == "scratch"


def test_no_stale_root_layout_duplicate():
    """The root icepi-layout.json must not exist — config/ is canonical."""
    stale = REPO_ROOT / "icepi-layout.json"
    assert not stale.exists(), (
        f"{stale} exists alongside config/icepi-layout.json — remove the duplicate"
    )


def test_slot_names_not_shadowed_by_global_aliases():
    """Global aliases must not shadow actual slot names."""
    layout = load_layout(REPO_ROOT / "config" / "icepi-layout.json")
    for slot_name in layout.slots:
        resolved = layout.resolve_slot(slot_name)
        assert resolved.name == slot_name, (
            f"resolve_slot({slot_name!r}) returned {resolved.name!r} — "
            f"a global alias is shadowing the slot name"
        )


def test_render_layout_lines():
    layout = load_layout(REPO_ROOT / "config" / "icepi-layout.json")
    lines = render_layout_lines(layout)
    assert any("boot" in line for line in lines)
    assert any("16777216" in line for line in lines)
