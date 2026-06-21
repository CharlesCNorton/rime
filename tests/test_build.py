"""Tests for icepi.build — project discovery, source collection, LPF, bitstream resolution."""


from icepi.build import (
    FIRMWARE_ROOT,
    IMAGES_ROOT,
    BuildError,
    available_projects,
    collect_sources,
    format_known_projects,
    materialize_lpf,
    resolve_bitstream_target,
    resolve_lpf,
)


def test_available_projects():
    projects = available_projects()
    assert "rime" in projects


def test_format_known_projects():
    text = format_known_projects()
    assert "rime" in text


def test_collect_sources_flash_test():
    sources = collect_sources(FIRMWARE_ROOT / "tests" / "flash_test")
    names = [s.name for s in sources]
    assert "top.sv" in names
    assert "uart_rx.sv" in names
    assert "uart_tx.sv" in names
    # flash_test does NOT instantiate flash_service
    assert "flash_service.sv" not in names


def test_resolve_lpf_direct():
    resolved = resolve_lpf(FIRMWARE_ROOT / "icepi-zero.lpf")
    assert resolved.exists()
    text = resolved.read_text(encoding="utf-8")
    assert "SYSCONFIG" in text


def test_materialize_lpf_disables_master_spi():
    project_dir = IMAGES_ROOT / "rime"
    build_lpf = materialize_lpf(project_dir, needs_flash_pins=True)
    assert build_lpf.exists()
    text = build_lpf.read_text(encoding="utf-8")
    assert "MASTER_SPI_PORT=DISABLE" in text
    assert "MASTER_SPI_PORT=ENABLE" not in text
    build_lpf.unlink()  # clean up


def test_materialize_lpf_keeps_master_spi():
    project_dir = IMAGES_ROOT / "rime"
    build_lpf = materialize_lpf(project_dir, needs_flash_pins=False)
    assert build_lpf.exists()
    text = build_lpf.read_text(encoding="utf-8")
    assert "MASTER_SPI_PORT=ENABLE" in text
    build_lpf.unlink()  # clean up


def test_resolve_bitstream_target_project_name():
    # Without --build, should fail if no bitstream exists
    # But if bitstream.bit is present it should resolve
    project_dir = IMAGES_ROOT / "rime"
    bitstream = project_dir / "bitstream.bit"
    if bitstream.exists():
        resolved = resolve_bitstream_target("rime")
        assert resolved.project == "rime"
        assert resolved.bitstream == bitstream.resolve()
        assert not resolved.built


def test_resolve_bitstream_target_nonexistent():
    try:
        resolve_bitstream_target("nonexistent_project_xyz")
        assert False, "should have raised"
    except FileNotFoundError:
        pass


def test_resolve_bitstream_target_bundle_rejected():
    try:
        resolve_bitstream_target("test.icepi.bundle.bin")
        assert False, "should have raised"
    except ValueError as exc:
        assert "bundle" in str(exc).lower()



def test_collect_sources_unknown_project():
    try:
        collect_sources(FIRMWARE_ROOT / "nonexistent")
        assert False, "should have raised"
    except (BuildError, FileNotFoundError):
        pass


def test_collect_sources_rime_no_false_module_deps():
    """RIME image must not pull in compositor modules via substring false positives.

    The build's source-collection scans the project text for module
    instantiations. Naive substring matching produces false positives like:
      - `latch.sv` matched by signal names like `spi_done_latch`
      - `mark.sv`  matched by `dmark` or other identifiers
      - `wire.sv`  matched by the Verilog `wire` keyword (the actual module
                   name is `wire_mod` per its manifest top_module field)
    The collector must use the manifest's top_module field and require an
    instantiation pattern `top_module ident(` to avoid these collisions.
    """
    sources = collect_sources(IMAGES_ROOT / "rime")
    names = [s.name for s in sources]
    assert "latch.sv" not in names, "latch.sv included via substring match on spi_done_latch etc."
    assert "mark.sv" not in names, "mark.sv included via substring match"
    assert "wire.sv" not in names, "wire.sv included via false match on Verilog `wire` keyword"
    # Sanity: the genuine sources are still pulled in.
    assert "rime_service.sv" in names
    assert "top.sv" in names
    assert "sd_install_engine.sv" in names  # cure list item #19 wired this in
    assert "auto_recovery.sv" in names


def test_auto_recovery_constants_agree_across_host_and_firmware():
    """Cure list item #16: AUTO_MAGIC, AUTO_CONTROL_LBA must
    agree across host (icepi/models.py) and firmware (auto_recovery.sv).

    Three sources of truth currently agree but nothing prevents drift.
    A wrong magic in the firmware would silently disable auto-recovery
    on every boot.
    """
    from icepi.tools import REPO_ROOT
    from icepi.models import AUTO_MAGIC, AUTO_CONTROL_LBA

    # AUTO_MAGIC = b"RIMEAUTO" -> 8 ASCII bytes -> 64-bit hex literal
    expected_magic_hex = AUTO_MAGIC.hex().upper()  # "52494D454155544F"

    auto_recovery = (REPO_ROOT / "firmware" / "core" / "auto_recovery.sv").read_text(encoding="utf-8")
    assert f"AUTO_MAGIC = 64'h{expected_magic_hex}" in auto_recovery, (
        f"firmware AUTO_MAGIC must be 64'h{expected_magic_hex} (= {AUTO_MAGIC!r})"
    )
    assert f"CTRL_LBA = 32'd{AUTO_CONTROL_LBA}" in auto_recovery, (
        f"firmware CTRL_LBA must be 32'd{AUTO_CONTROL_LBA}"
    )


def test_bundle_magic_agrees_across_host_and_firmware():
    """Cure list item #16: BUNDLE_MAGIC must agree across icepi/models.py
    and firmware/core/sd_install_engine.sv. The install engine validates
    the magic at the start of every SD bundle install; a mismatch would
    reject every legitimate bundle as malformed.
    """
    from icepi.tools import REPO_ROOT
    from icepi.models import BUNDLE_MAGIC

    expected_magic_hex = BUNDLE_MAGIC.hex().upper()  # "4943455049423100"

    install_engine = (REPO_ROOT / "firmware" / "core" / "sd_install_engine.sv").read_text(encoding="utf-8")
    assert f"BUNDLE_MAGIC = 64'h{expected_magic_hex}" in install_engine, (
        f"firmware BUNDLE_MAGIC must be 64'h{expected_magic_hex} (= {BUNDLE_MAGIC!r})"
    )


def test_strip_bitstream_header():
    from icepi.tools import strip_bitstream_header

    comment = b"\xff\x00Part: LFE5U-25F\x00"
    config = b"\xff\xff\xff\xbd\xb3" + bytes(range(32))
    assert strip_bitstream_header(comment + config) == config
    assert strip_bitstream_header(config) == config  # idempotent
    assert strip_bitstream_header(b"\x01\x02\x03\x04") == b"\x01\x02\x03\x04"  # no sync word


def test_no_external_use_of_private_exchange():
    """Cure list item #12: only icepi/flash_service.py may call FlashService._exchange.

    External callers (the shell `raw` builtin, regression tests, etc.) must
    use the public `raw_exchange` method. Cross-module use of private (leading
    underscore) APIs is a maintenance landmine and was the situation that
    motivated this rule.
    """
    import re
    from icepi.tools import REPO_ROOT
    pattern = re.compile(r"\b(svc|service|self)\._exchange\b")
    offenders = []
    for root in (REPO_ROOT / "icepi", REPO_ROOT / "tests", REPO_ROOT / "modules", REPO_ROOT / "scripts"):
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if py.parts[-2:] == ("icepi", "flash_service.py"):
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(text):
                offenders.append(f"{py.relative_to(REPO_ROOT)}:{text[:match.start()].count(chr(10))+1}")
    assert offenders == [], (
        "Cross-module callers must use FlashService.raw_exchange, not _exchange:\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_no_module_has_zero_lut_manifest():
    """Cure list item #10/11: no module declares 0 LUTs and 0 multipliers.

    Before the manifest refresh, MORTAR declared {luts: 0, multipliers: 0}
    even though the README said "DSP-only". A 0-everything manifest is
    always wrong; it means the budget was never measured.
    """
    import json
    from icepi.tools import REPO_ROOT
    offenders = []
    for d in (REPO_ROOT / "modules").iterdir():
        if not d.is_dir() or d.name == "rime-i":
            continue
        mj = d / "module.json"
        if not mj.exists():
            continue
        data = json.loads(mj.read_text(encoding="utf-8"))
        r = data.get("resources", {})
        if r.get("luts", 0) == 0 and r.get("multipliers", 0) == 0:
            offenders.append(d.name)
    assert offenders == [], (
        "Modules with luts=0 and multipliers=0 manifests (run "
        "`python scripts/verify_manifest_luts.py --update` to refresh):\n"
        + "\n".join(f"  {m}" for m in offenders)
    )


def test_gauge_no_placeholder_register_slots():
    """Cure list item #9: GAUGE register slots 0x008 (READS) and 0x00C (WRITES)
    must return real read/write counters, not the hardcoded 0 placeholders.
    """
    from icepi.tools import REPO_ROOT
    sv = (REPO_ROOT / "modules" / "gauge" / "gauge.sv").read_text(encoding="utf-8")
    assert "(placeholder)" not in sv, "GAUGE still has placeholder register slots"
    assert "snoop_wstrb" in sv, "GAUGE missing snoop_wstrb input port"
    assert "read_count" in sv, "GAUGE missing read_count signal"
    assert "write_count" in sv, "GAUGE missing write_count signal"
    assert "result_reads" in sv, "GAUGE missing result_reads signal"
    assert "result_writes" in sv, "GAUGE missing result_writes signal"


def test_snoop_modules_all_declare_wstrb_port():
    """Cure list item #9 corollary: every module that uses the snoop interface
    must declare the snoop_wstrb input port. compose.py wires mem_wstrb to
    every snoop module unconditionally, so any module declaring snoop_addr
    without snoop_wstrb would fail synthesis with 'unknown port' error.
    """
    import json
    from icepi.tools import REPO_ROOT
    snoop_modules = []
    for mod_dir in (REPO_ROOT / "modules").iterdir():
        if not mod_dir.is_dir():
            continue
        mj = mod_dir / "module.json"
        if not mj.exists():
            continue
        data = json.loads(mj.read_text(encoding="utf-8"))
        requires = [r.lower() for r in data.get("interfaces", {}).get("requires", [])]
        if "snoop" not in requires:
            continue
        for sv in mod_dir.glob("*.sv"):
            if sv.name == "top.sv":
                continue
            text = sv.read_text(encoding="utf-8")
            if "snoop_addr" in text:
                snoop_modules.append((mod_dir.name, sv.name, "snoop_wstrb" in text))
    missing = [(m, s) for m, s, ok in snoop_modules if not ok]
    assert missing == [], (
        "Snoop modules missing snoop_wstrb input port:\n"
        + "\n".join(f"  {m}/{s}" for m, s in missing)
    )
    assert len(snoop_modules) >= 6, f"expected >=6 snoop modules, found {len(snoop_modules)}"


def test_compose_rejects_rime_i_listed_as_module():
    """Cure list item #7: validate_composition must not double-count rime-i.

    rime-i's resources (RIME_I_LUTS = 4050, RIME_I_BRAMS = 7) are added
    unconditionally to every composition. If rime-i also appears in the
    module name list, the validator double-counts those LUTs and the
    generated top.sv would emit two `rime_i_core CPU` instantiations
    that synthesis would reject for name conflict.
    """
    from icepi.compose import validate_composition, CompositionError
    try:
        validate_composition(["rime-i", "anvil"])
    except CompositionError as exc:
        assert "rime-i" in str(exc) and "implicit" in str(exc).lower()
        return
    raise AssertionError("should have raised CompositionError")


def test_compose_lut_budget_matches_constants():
    """Cure list item #7 corollary: LUT budget should equal RIME_I + overhead + module sum."""
    from icepi.compose import validate_composition, RIME_I_LUTS, PLATFORM_OVERHEAD_LUTS, load_module_spec
    plan = validate_composition(["anvil"])
    anvil_luts = load_module_spec("anvil").luts
    expected = RIME_I_LUTS + PLATFORM_OVERHEAD_LUTS + anvil_luts
    assert plan.total_luts == expected, (
        f"compose budget {plan.total_luts} != expected {expected} "
        f"({RIME_I_LUTS} CPU + {PLATFORM_OVERHEAD_LUTS} overhead + {anvil_luts} anvil)"
    )


def test_no_stale_build_flags_in_subprocess_calls():
    """Every subprocess invocation of icepi_helper.py build must use only currently-supported flags.

    This catches cases like the deleted --synth flag still being referenced
    in module test runners (cure list item #1 / commit be265bf cleanup).
    """
    import re
    from icepi.tools import REPO_ROOT

    # Build the set of flags the parser actually accepts for the `build` subcommand.
    from icepi_helper import build_parser
    parser = build_parser()
    build_subparser = None
    for action in parser._subparsers._actions:  # noqa: SLF001
        if hasattr(action, 'choices') and action.choices and 'build' in action.choices:
            build_subparser = action.choices['build']
            break
    assert build_subparser is not None, "could not introspect build subparser"
    accepted_flags = set()
    for act in build_subparser._actions:  # noqa: SLF001
        for opt in getattr(act, 'option_strings', ()):
            accepted_flags.add(opt)

    # Scan every Python file under modules/, scripts/, tests/ for build invocations.
    pattern = re.compile(r'icepi_helper\.py["\'\s,)]+.*?["\']build["\'].*?\)', re.DOTALL)
    flag_pattern = re.compile(r'["\'](--[a-z][a-z0-9_-]*)["\']')
    offenders = []
    for root in (REPO_ROOT / 'modules', REPO_ROOT / 'scripts', REPO_ROOT / 'tests'):
        if not root.exists():
            continue
        for py in root.rglob('*.py'):
            text = py.read_text(encoding='utf-8', errors='ignore')
            for match in pattern.finditer(text):
                blob = match.group(0)
                for flag_match in flag_pattern.finditer(blob):
                    flag = flag_match.group(1)
                    if flag not in accepted_flags:
                        offenders.append((py.relative_to(REPO_ROOT), flag))
    assert offenders == [], (
        "build subprocess calls reference flags the parser does not accept:\n"
        + "\n".join(f"  {p}: {f}" for p, f in offenders)
    )
