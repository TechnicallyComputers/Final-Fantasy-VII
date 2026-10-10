#!/usr/bin/env python3
"""Execute original FFVII accessors to check the developer extended-query ABI.

Needs Unicorn and the shared test bridge built from tests/test_ff7_party_access.c
plus src/ff7_party.c. Reads only owner disc bytes. The isolated oracle VM seeds
synthetic alias/party lookup entries so ORIGINAL instructions address an extra
record in Expansion 1. The runtime adapter never patches those native tables.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import random
import re
import struct

from inspect_ff7_party import Disc, EXE_SHA1, ROOT, kernel_sections
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC

FUNCTIONS = {"name": (0x800257CC, 13), "armor": (0x80025668, 29), "weapon": (0x800256DC, 31)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--disc", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=256)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.cases < 128:
        parser.error("Use at least128 cases to exercise every original weapon ID")
    disc = Disc(args.disc)
    try:
        boots = [name for name in disc.files if name.startswith("SCUS_") and "/" not in name]
        if len(boots) != 1:
            raise ValueError("Expected exactly one NTSC-U boot executable")
        exe = disc.read(boots[0])
        kernel = kernel_sections(disc.read("INIT/KERNEL.BIN"))
    finally:
        disc.reader.close()
    if hashlib.sha1(exe).hexdigest() != EXE_SHA1:
        raise ValueError("Unsupported original executable")
    assert len(kernel[5]) == 128 * 44 and len(kernel[6]) == 32 * 36
    template = kernel[3][7 * 132:8 * 132]
    assert template[0] == 10
    source = (ROOT / "src/ff7_party_access.c").read_text()
    guards = {}
    for name, (address, count) in FUNCTIONS.items():
        values = re.search(r"s_" + name + r"_words\[\]\s*=\s*\{([^}]+)\}", source).group(1)
        words = [int(word, 16) for word in re.findall(r"0x[0-9a-fA-F]+", values)]
        data = exe[0x800 + address - 0x80010000:0x800 + address - 0x80010000 + count * 4]
        assert len(words) == count and data == struct.pack(f"<{count}I", *words), name
        guards[name] = {"address": f"0x{address:08X}", "words": count,
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    library = ctypes.CDLL(str(args.library.resolve()))
    library.ff7_test_access_publish.argtypes = [ctypes.c_void_p]
    library.ff7_test_access_query.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
    library.psx_mod_read_byte.argtypes = [ctypes.c_uint32]
    library.psx_mod_read_byte.restype = ctypes.c_uint8
    library.ff7_test_access_reset()
    original = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    original.mem_map(0, 0x200000)
    original.mem_map(0x1F000000, 0x1000)
    original.mem_write(0x10000, exe[0x800:])
    original.mem_write(0x71E44, kernel[6])
    original.mem_write(0x738A0, kernel[5])
    # Solve native_record_base +132*index == expansion_base modulo2^32.
    # This is an isolated execution fixture, not a proposed runtime alias hack.
    index = (((0x9F000000 - 0x8009C738) // 4) * pow(33, -1, 1 << 30)) % (1 << 30)
    assert (0x8009C738 + 132 * index) & 0xFFFFFFFF == 0x9F000000
    original.mem_write(0x491D0 + 256 * 4, struct.pack("<I", index))
    original.mem_write(0x9CBDC + 256, b"\x0a")
    original.mem_write(0x491D0 + 10 * 4, struct.pack("<I", index))
    rng = random.Random(94163)
    comparisons = 0
    for case in range(args.cases):
        record = bytearray(template)
        record[0x1C], record[0x1D] = case % 128, case % 32
        assert library.ff7_test_access_publish(bytes(record))
        original.mem_write(0x1F000000, bytes(record))
        for name, (address, _) in FUNCTIONS.items():
            registers = [rng.randrange(1 << 32) for _ in range(32)]
            registers[0], registers[4], registers[31] = 0, 256, 0x80001000
            for r, value in enumerate(registers):
                original.reg_write(UC_MIPS_REG_0 + r, value)
            original.emu_start(address, 0x80001000, count=128)
            expected = [original.reg_read(UC_MIPS_REG_0 + r) for r in range(32)]
            host = (ctypes.c_uint32 * 32)(*registers)
            pc = ctypes.c_uint32(address)
            assert library.ff7_test_access_query(address, host, ctypes.byref(pc)) == 1
            if list(host) != expected or pc.value != original.reg_read(UC_MIPS_REG_PC):
                raise AssertionError(f"{name} GPR/link-return mismatch case{case}")
            expected_pointer = (0x9F000010 if name == "name" else
                                0x80071E4D + record[0x1D] * 36 if name == "armor" else
                                0x800738BC + record[0x1C] * 44)
            assert host[2] == expected_pointer
            if name == "name":
                host_bytes = bytes(library.psx_mod_read_byte(host[2] + i) for i in range(12))
                assert host_bytes == bytes(original.mem_read(host[2] & 0x1FFFFFFF, 12))
            comparisons += 1
    result = {"status": "developer-query-ABI-verified-not-playable",
              "schema": "ff7 party accessor evidence v1",
              "program_sha1": EXE_SHA1, "guards": guards,
              "cases": args.cases, "original_mips_calls": comparisons,
              "all_32_gprs_and_link_return_match": True,
              "equipment_ids_exercised": {"armor": 32, "weapon": 128},
              "original_sephiroth_equipment": {
                  "weapon_id": template[0x1C], "armor_id": template[0x1D],
                  "weapon_equip_mask": hex(struct.unpack_from("<H", kernel[5], template[0x1C]*44+14)[0]),
                  "weapon_slot_bytes": list(kernel[5][template[0x1C]*44+28:template[0x1C]*44+36]),
                  "armor_slot_bytes": list(kernel[6][template[0x1D]*36+9:template[0x1D]*36+17])},
              "format_reference": "https://wiki.ffrtt.ru/index.php/FF7/Weapon_data",
              "guest_storage": "Framework psx_mod_alloc_guest_memory, Expansion1; no guessed main-RAM address",
              "query_abi": {
                  "native": "Every a0<0x100 declines with all GPRs unchanged; stock function executes.",
                  "extended_input": "a0=published extra identity0x100..0xFFFE; equipment functions extend original party-slot ABI.",
                  "name_success": "v0=extra_record+0x10; at=0x800491D0+identity*4; v1=0x8009C748; a0=identity*4",
                  "armor_success": "v0=0x80071E4D+armorID*36; at=extra_record+0x1D; v1=0x80071E4D; a0 unchanged",
                  "weapon_success": "v0=0x800738BC+weaponID*44; at=extra_record+0x1C; v1=0x800738BC; a0 unchanged",
                  "extended_error": "Consumes unsupported query with v0=0; all other GPRs unchanged.",
                  "return": "All consumed calls return PC=ra through runtime filter dispatch; remaining GPRs unchanged."},
              "blockers": [
                  "PHS init/enumeration cap9 at0x801D0C5C/0x801D0DFC, byte reserve grid0x801D3424, portrait alias use0x801D18E4 need separate host identity mapping.",
                  "EQIPMENU cached record base store0x801D6D0C and hardcoded reads0x801D0740/0x801D0778 bypass these query functions; not redirected.",
                  "EQIPMENU guestID10 branch0x801D7770 and MGICMENU level read0x801D1BD4/ID10 MP branch0x801D1C6C require per-context adapters.",
                  "Battle name cache0x800DD654..0x800DD65C and record read0x800E350C bypass GetCharacterName; AI/control/stats/rewards need independent actor binding.",
                  "Field/story byte party IDs, forced-party transitions and actor models have no validated extended-identity adapter yet.",
                  "Equipment compatibility, actual materia transfers, native fallback saves and gameplay ownership/rewind synchronization remain unfinished."],
              "oracle_fixture": "Synthetic lookup entries only in isolated Unicorn VM; runtime changes no native alias or party table.",
              "remaining": "PHS/menu/battle callers still require explicit conversion to 16-bit identities and complete read/write adapters."}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
