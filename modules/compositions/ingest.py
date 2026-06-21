#!/usr/bin/env python3
"""DATA image regression: Ingest.

Exercises all 13 modules of the data composition with known inputs
and prints labelled hex readbacks.

Usage:
    python modules/compositions/ingest.py --gen-only
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rime-i"))

_gf_src = (Path(__file__).resolve().parent.parent / "rime-i" / "gen_firmware.py").read_text()
_gf_ns = {}
exec(_gf_src.split("\ndef generate_math_firmware")[0], _gf_ns)
RV32I = _gf_ns["RV32I"]

x0, ra, sp = 0, 1, 2
t0, t1, t2 = 5, 6, 7
a0, a1 = 10, 11
s0, s1, s2, s3, s4, s5, s6, s7 = 8, 9, 18, 19, 20, 21, 22, 23

UART = 0x20000000

APEX   = 0x30000000
AXIOM  = 0x31000000
CAIRN  = 0x32000000
CODEC  = 0x33000000
DELTA  = 0x34000000
HALO   = 0x35000000
MIRROR = 0x36000000
PACK   = 0x37000000
PARSE  = 0x38000000
QUILL  = 0x39000000
RANK   = 0x3A000000
RUNE   = 0x3B000000
SIFT   = 0x3C000000

DATA_MODULES = [
    "apex", "axiom", "cairn", "codec", "delta", "halo", "mirror",
    "pack", "parse", "quill", "rank", "rune", "sift",
]


def emit_prelude(asm):
    asm.lui(sp, 0x00001)
    asm.lui(s4, 0x20000)
    asm.j("main")

    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    asm.label("puthex")
    asm.addi(sp, sp, -12)
    asm.sw(ra, sp, 8)
    asm.sw(s0, sp, 4)
    asm.sw(s1, sp, 0)
    asm.mv(s0, a0)
    asm.addi(s1, x0, 28)
    asm.label("ph_loop")
    asm.blt(s1, x0, "ph_done")
    asm.srl(a0, s0, s1)
    asm.andi(a0, a0, 0xF)
    asm.addi(t0, x0, 10)
    asm.blt(a0, t0, "ph_digit")
    asm.addi(a0, a0, ord('A') - 10)
    asm.j("ph_emit")
    asm.label("ph_digit")
    asm.addi(a0, a0, ord('0'))
    asm.label("ph_emit")
    asm.call("putc")
    asm.addi(s1, s1, -4)
    asm.j("ph_loop")
    asm.label("ph_done")
    asm.lw(s1, sp, 0)
    asm.lw(s0, sp, 4)
    asm.lw(ra, sp, 8)
    asm.addi(sp, sp, 12)
    asm.ret()


def print_label(asm, label, value_reg):
    for ch in label:
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, ord(':'))
    asm.call("putc")
    asm.mv(a0, value_reg)
    asm.call("puthex")
    asm.addi(a0, x0, 10)
    asm.call("putc")


def generate_firmware():
    asm = RV32I()
    emit_prelude(asm)

    asm.label("main")

    # HALO: clear, push 4 values, read COUNT
    asm.li(t0, HALO + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    for v in [0x11, 0x22, 0x33, 0x44]:
        asm.li(t0, HALO + 0x000)
        asm.addi(t1, x0, v)
        asm.sw(t1, t0, 0)
    asm.li(t0, HALO + 0x010)
    asm.lw(s0, t0, 0)
    print_label(asm, "HALO", s0)

    # CAIRN: clear, push 3 values, read DEPTH
    asm.li(t0, CAIRN + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, CAIRN + 0x000)
    asm.addi(t1, x0, 0x55)
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 0x33)
    asm.sw(t1, t0, 0)
    asm.li(t1, 0x7AA)
    asm.sw(t1, t0, 0)
    asm.li(t0, CAIRN + 0x010)
    asm.lw(s0, t0, 0)
    print_label(asm, "CAIRN", s0)

    # RANK: sort [5,3,8,1,7,2,6,4]
    asm.li(t0, RANK + 0x040)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    for i, v in enumerate([5, 3, 8, 1, 7, 2, 6, 4]):
        asm.li(t0, RANK + i * 4)
        asm.addi(t1, x0, v)
        asm.sw(t1, t0, 0)
    asm.li(t0, RANK + 0x040)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, RANK + 0x020)
    asm.lw(s0, t0, 0)
    print_label(asm, "RANK", s0)

    # CODEC: encode "Man" -> "TWFu"
    asm.li(t0, CODEC + 0x02C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, CODEC + 0x000)
    asm.addi(t1, x0, ord('M'))
    asm.sw(t1, t0, 0)
    asm.li(t0, CODEC + 0x004)
    asm.addi(t1, x0, ord('a'))
    asm.sw(t1, t0, 0)
    asm.li(t0, CODEC + 0x008)
    asm.addi(t1, x0, ord('n'))
    asm.sw(t1, t0, 0)
    asm.li(t0, CODEC + 0x010)
    asm.lw(s0, t0, 0)
    print_label(asm, "CODEC", s0)

    # RUNE: render 'A' row 0
    asm.li(t0, RUNE + 0x000)
    asm.addi(t1, x0, ord('A'))
    asm.sw(t1, t0, 0)
    asm.li(t0, RUNE + 0x004)
    asm.sw(x0, t0, 0)
    asm.li(t0, RUNE + 0x008)
    asm.lw(s0, t0, 0)
    print_label(asm, "RUNE", s0)

    # AXIOM: feed JSON `{"k":1}` (7 bytes), read DEPTH after lbrace
    asm.li(t0, AXIOM + 0x00C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, AXIOM + 0x000)
    for ch in b'{"k":1}':
        asm.addi(t1, x0, ch)
        asm.sw(t1, t0, 0)
    asm.li(t0, AXIOM + 0x008)
    asm.lw(s0, t0, 0)              # DEPTH at end (back to 0 after rbrace)
    print_label(asm, "AXIOM", s0)
    asm.li(t0, AXIOM + 0x010)
    asm.lw(s0, t0, 0)              # OFFSET = bytes processed
    print_label(asm, "AXIOMOFF", s0)

    # DELTA: compare two 4-byte streams: [1,2,3,4] vs [1,2,3,5]
    asm.li(t0, DELTA + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, DELTA + 0x000)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # OLD
    asm.li(t0, DELTA + 0x004)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # NEW (same)
    asm.li(t0, DELTA + 0x000)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, DELTA + 0x004)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, DELTA + 0x000)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)
    asm.li(t0, DELTA + 0x004)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)
    asm.li(t0, DELTA + 0x000)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)
    asm.li(t0, DELTA + 0x004)
    asm.addi(t1, x0, 5)
    asm.sw(t1, t0, 0)              # different
    asm.li(t0, DELTA + 0x00C)
    asm.lw(s0, t0, 0)              # CHANGED
    print_label(asm, "DELTA", s0)

    # MIRROR: 4 entries, query a key matching entry 2
    # Configure: KEY[2]=0xCAFE0000, MASK[2]=0xFFFF0000, VALUE[2]=0xDEADBEEF, VALID[2]=1
    asm.li(t0, MIRROR + 0x108)     # KEY[2]
    asm.li(t1, 0xCAFE0000)
    asm.sw(t1, t0, 0)
    asm.li(t0, MIRROR + 0x148)     # MASK[2]
    asm.li(t1, 0xFFFF0000)
    asm.sw(t1, t0, 0)
    asm.li(t0, MIRROR + 0x188)     # VALUE[2]
    asm.li(t1, 0xDEADBEEF)
    asm.sw(t1, t0, 0)
    asm.li(t0, MIRROR + 0x1C8)     # VALID[2]
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, MIRROR + 0x000)
    asm.li(t1, 0xCAFE1234)         # query — high half matches entry 2
    asm.sw(t1, t0, 0)
    asm.li(t0, MIRROR + 0x004)
    asm.lw(s0, t0, 0)              # RESULT
    print_label(asm, "MIRROR", s0)

    # PACK: feed run of 5 'A' bytes, read OUTPUT and STATUS
    asm.li(t0, PACK + 0x008)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, PACK + 0x000)
    asm.addi(t1, x0, ord('A'))
    for _ in range(5):
        asm.sw(t1, t0, 0)
    asm.li(t0, PACK + 0x008)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # flush
    asm.li(t0, PACK + 0x00C)
    asm.lw(s0, t0, 0)              # STATUS - output FIFO count
    print_label(asm, "PACK", s0)

    # PARSE: configure single state matching 'R', feed 'RIME', read MATCHES
    asm.li(t0, PARSE + 0x008)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, PARSE + 0x100)      # STATE_CFG[0]
    # match='R'(0x52), next_match=0, next_nomatch=7(stay), accept=1, active=1
    asm.li(t1, 0xC052 | (0 << 8) | (7 << 11))
    asm.sw(t1, t0, 0)
    asm.li(t0, PARSE + 0x000)
    for ch in b"RIMER":
        asm.addi(t1, x0, ch)
        asm.sw(t1, t0, 0)
    asm.li(t0, PARSE + 0x00C)
    asm.lw(s0, t0, 0)              # MATCHES
    print_label(asm, "PARSE", s0)

    # QUILL: write 3 bytes to channel 0, read COUNT
    asm.li(t0, QUILL + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # clear
    asm.li(t0, QUILL + 0x004)
    asm.sw(x0, t0, 0)              # CHANNEL = 0
    asm.li(t0, QUILL + 0x000)
    asm.addi(t1, x0, 0xAA)
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 0xBB)
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 0xCC)
    asm.sw(t1, t0, 0)
    asm.li(t0, QUILL + 0x010)
    asm.lw(s0, t0, 0)              # COUNT
    print_label(asm, "QUILL", s0)

    # SIFT: insert 0xDEADBEEF, query same -> should be present
    asm.li(t0, SIFT + 0x008)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # clear
    asm.li(t0, SIFT + 0x000)
    asm.li(t1, 0xDEADBEEF)
    asm.sw(t1, t0, 0)              # insert
    asm.li(t0, SIFT + 0x004)
    asm.li(t1, 0xDEADBEEF)
    asm.sw(t1, t0, 0)              # query
    asm.lw(s0, t0, 0)              # result (should be 1)
    print_label(asm, "SIFT", s0)

    # APEX: clear, push 3 entries with priorities, read COUNT
    asm.li(t0, APEX + 0x018)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # clear
    for val, pri in [(0x1234, 5), (0x5678, 2), (0xABCD, 8)]:
        asm.li(t0, APEX + 0x000)
        asm.li(t1, val)
        asm.sw(t1, t0, 0)
        asm.li(t0, APEX + 0x004)
        asm.addi(t1, x0, pri)
        asm.sw(t1, t0, 0)          # PUSH_PRI triggers insert
    asm.li(t0, APEX + 0x014)
    asm.lw(s0, t0, 0)              # COUNT
    print_label(asm, "APEX", s0)

    for ch in "INGEST:DONE":
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, 10)
    asm.call("putc")

    asm.li(t0, 0x100000)
    asm.label("_final_delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "_final_delay")
    asm.j("main")

    asm.resolve()
    return asm.code


def predict():
    return {
        "HALO":     4,            # count after 4 pushes
        "CAIRN":    3,            # depth after 3 pushes
        "RANK":     1,            # sorted[0] of [5,3,8,1,7,2,6,4]
        "CODEC":    ord('T'),     # base64('Man')[0]
        "RUNE":     None,         # font glyph row, HDL-specific
        "AXIOM":    0,            # depth back to 0 after balanced braces
        "AXIOMOFF": 7,            # 7 bytes processed
        "DELTA":    1,            # 1 changed byte (4!=5)
        "MIRROR":   0xDEADBEEF,   # query matches entry 2
        "PACK":     None,         # FIFO count varies with HDL encoding
        "PARSE":    None,         # accept count depends on NFA bit layout
        "QUILL":    3,            # 3 bytes pushed
        "SIFT":     1,            # bloom filter hit
        "APEX":     3,            # 3 entries pushed
    }


def main():
    firmware = generate_firmware()
    print(f"Ingest firmware: {len(firmware)} instructions ({len(firmware)*4} bytes)")
    print(f"BRAM usage: {len(firmware)}/1024 ({len(firmware)*100//1024}%)")
    expected = predict()
    print("Expected:")
    for label, val in expected.items():
        if val is None:
            print(f"  {label:9s}: variable")
        else:
            print(f"  {label:9s}: 0x{val:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
