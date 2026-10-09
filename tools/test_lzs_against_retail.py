#!/usr/bin/env python3
"""Compare our LZS implementation with the owner's original MIPS routine.

Requires capstone-free Unicorn (pip install unicorn) and a locally compiled
shared library exporting ff7_lzs_decode. No original assets are distributed.
Checks output RAM and every GPR using randomized streams and original assets.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "psxrecomp" / "tools"))
from aot_overlay_pipeline import Disc
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_0


def generated_stream(rng):
    payload, output_size = bytearray(), 0
    for _ in range(rng.randint(0, 32)):
        flags, tokens = 0, bytearray()
        for bit in range(8):
            if rng.random() < 0.5 or not output_size:
                flags |= 1 << bit
                tokens.append(rng.randrange(256))
                output_size += 1
            else:
                distance = rng.randint(1, min(4095, output_size + 16))
                length = rng.randint(3, 18)
                index = (output_size + 0xFEE - distance) & 0xFFF
                tokens.extend((index & 255, ((index >> 4) & 0xF0) | (length - 3)))
                output_size += max(length, distance - output_size)
        payload.append(flags)
        payload.extend(tokens)
    return struct.pack("<I", len(payload)) + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--disc", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=600)
    args = parser.parse_args()
    disc = Disc(args.disc)
    exe = disc.read("SCUS_941.63")
    if hashlib.sha1(exe).hexdigest() != "a95e8b16b97071203b953bb81a33980509262f30":
        raise ValueError("Unsupported original executable")
    library = ctypes.CDLL(str(args.library.resolve()))
    decode = library.ff7_lzs_decode
    decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                       ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32,
                       ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_size_t)]
    rng = random.Random(94163)
    assets = [name for name in disc.files if name in (
        "ENEMY6/SEFIROS.LZS", "STARTUP/SCEAP.LZS")]
    streams = [(f"generated {n}", generated_stream(rng)) for n in range(args.cases)]
    streams += [(name, disc.read(name)) for name in assets]
    def check_case(label, source, src=0x80100000, dst=0x80140000):
        capacity = 0xC0000
        if (src & 0x1FFFFFFF) + len(source) > 0x200000:
            raise ValueError(f"Oracle input leaves RAM: {label}")
        registers = [rng.randrange(1 << 32) for _ in range(32)]
        registers[0], registers[4], registers[5], registers[31] = 0, src, dst, 0x80001000
        original = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        original.mem_map(0, 0x200000)
        original.mem_write(0x10000, exe[0x800:])
        original.mem_write(src & 0x1FFFFFFF, source)
        for index, value in enumerate(registers):
            original.reg_write(UC_MIPS_REG_0 + index, value)
        original.emu_start(0x80034BB0, 0x80001000, count=20000000)
        expected = [original.reg_read(UC_MIPS_REG_0 + index) for index in range(32)]
        output = ctypes.create_string_buffer(capacity)
        host = (ctypes.c_uint32 * 32)(*registers)
        written = ctypes.c_size_t()
        if not decode(source, len(source), output, capacity, src, dst, host,
                      ctypes.byref(written)):
            raise AssertionError(f"Host decoder declined {label}")
        if list(host) != expected:
            raise AssertionError(f"Register mismatch in {label}")
        if output.raw[:written.value] != bytes(original.mem_read(dst & 0x1FFFFFFF, written.value)):
            raise AssertionError(f"Output mismatch in {label}")
        return written.value

    sizes = {label: check_case(label, source) for label, source in streams}
    overlap_cases = 0
    for name in assets:
        source = disc.read(name)
        offset = (sizes[name] - len(source) // 2) & ~3
        if offset <= 0:
            raise ValueError(f"No bounded oracle overlap candidate: {name}")
        for destination in (0x80140000, 0xA0140000):
            check_case(name + " streaming overlap", source, 0x80140000 + offset,
                       destination)
            overlap_cases += 1
    literal = struct.pack("<I", 9) + b"\xffABCDEFGH"
    check_case("literal in-place", literal, 0x80140000, 0x80140000)
    overlap_cases += 1
    # The observed startup call overwrites unread input, unlike the simpler
    # streaming placements above. Compare the exact real guest addresses.
    startup = disc.read("STARTUP/SCEAP.LZS")
    for destination in (0x80100000, 0xA0100000):
        check_case("observed startup overlap", startup, 0x80180000, destination)
        overlap_cases += 1
    # Unsupported inputs must leave the published register array unchanged.
    for source, capacity in [(b"", 32), (b"\x02\0\0\0\0\x12", 32),
                             (b"\x03\0\0\0\0\xee\xf0", 32),
                             (b"\x02\0\0\0\1X", 0)]:
        host = (ctypes.c_uint32 * 32)(*range(32))
        output, written = ctypes.create_string_buffer(32), ctypes.c_size_t()
        if decode(source, len(source), output, capacity, 0x80100000, 0x80110000,
                  host, ctypes.byref(written)) or list(host) != list(range(32)):
            raise AssertionError("Unsupported input did not decline transactionally")
    empty = b"\0\0\0\0"
    output = ctypes.create_string_buffer(32)
    if decode(empty, len(empty), output, 32, 0x80100000, 0x80110000,
              None, ctypes.byref(ctypes.c_size_t())):
        raise AssertionError("Null register array did not decline")
    unsafe = struct.pack("<I", 5) + b"\x01X\xee\xff\0"
    for destination in (0x80140000, 0xA0140000):
        host = (ctypes.c_uint32 * 32)(*range(32))
        if decode(unsafe, len(unsafe), output, 32, 0x80140000, destination,
                  host, ctypes.byref(ctypes.c_size_t())) or list(host) != list(range(32)):
            raise AssertionError("Mutated truncated input did not decline transactionally")
    print(f"PASS: {args.cases} randomized streams + {len(assets)} original assets; "
          f"{overlap_cases} overlap/alias cases; output RAM and all 32 GPRs match "
          "retail MIPS; unsupported inputs decline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
