"""`swap` command: compose rime-i + modules and SRAM-load the result onto the
board over JTAG, without rewriting flash. The composition is volatile — a
`reload` (or power cycle) restores the flashed resident app.

ECP5 has no in-fabric partial reconfiguration in the open toolchain, so this
swaps the whole composed image rather than one module in place; "without a
full reflash" means the SRAM is reconfigured and flash is left untouched.
"""

from __future__ import annotations

import argparse

from icepi.commands.observe import _imports, _emit_io, _emit_line, _emit_print_hex
from icepi.compose import generate_and_build, validate_composition, MODULES_ROOT

__all__ = ["cmd_swap"]


def _gen_banner_firmware(R, module_count):
    a = R["RV32I"]()
    sp, s4, t0, x0, s2 = R["sp"], R["s4"], R["t0"], R["x0"], R["s2"]
    a.lui(sp, 0x00001); a.lui(s4, 0x20000); a.j("main")
    _emit_io(a, R)
    a.label("main")
    _emit_line(a, R, "SWAP")
    a.li(s2, module_count)
    _emit_print_hex(a, R, s2)
    _emit_line(a, R, "END")
    a.li(t0, 0x200000); a.label("sd"); a.addi(t0, t0, -1); a.bne(t0, x0, "sd"); a.j("main")
    a.resolve()
    return a.code


def cmd_swap(args):
    R = _imports()
    modules = args.modules
    plan = validate_composition(modules)
    print(f"swap: composing rime-i + {modules}")
    print(f"  budget: {plan.total_luts}/{plan.available_luts} LUTs, "
          f"{plan.total_brams}/{plan.available_brams} BRAMs, "
          f"{plan.total_mults}/{plan.available_mults} DSPs")
    print(f"  address map: {plan.address_map}")
    fw = _gen_banner_firmware(R, len(modules))
    _plan, bitstream = generate_and_build(
        modules, fw, output_dir=MODULES_ROOT / "compositions", clean=args.clean
    )
    print(f"  built: {bitstream}")
    from compositor_test import flash_and_read, restore_rime  # type: ignore
    print("  SRAM-loading composition over JTAG (flash untouched, volatile)")
    out = flash_and_read("compositions")
    live = "SWAP" in out
    first = next((l for l in out.splitlines() if l.strip()), "")
    print(f"  composition {'is live' if live else 'did NOT report alive'} (banner: {first!r})")
    restored = False
    if getattr(args, "restore", False):
        restore_rime()
        restored = True
        print("  restored the flashed app over JTAG")
    else:
        print("  note: volatile SRAM image; run `reload` to restore the flashed app")
    return {"modules": modules, "bitstream": str(bitstream), "live": live,
            "address_map": plan.address_map, "restored": restored}
