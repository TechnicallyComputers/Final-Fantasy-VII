#!/usr/bin/env python3
"""Read-only NTSC-U party-storage evidence from the owner's original disc.

Reads the framework's ISO reader, original binary bytes, and our symbol address
map. Never downloads or opens decompilation source. Reports metadata and short
instruction-site evidence, not extracted game assets. Candidate MIPS constant
references can occur in data; they are NOT verified patch recipes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tomllib
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "psxrecomp" / "tools"))
from aot_overlay_pipeline import Disc  # noqa: E402

EXE_SHA1 = "a95e8b16b97071203b953bb81a33980509262f30"
NAME_WORDS = (
    0x00042080, 0x3C018005, 0x242191D0, 0x00240821, 0x8C230000,
    0x00000000, 0x00031140, 0x00431021, 0x00021080, 0x3C03800A,
    0x2463C748, 0x03E00008, 0x00431021,
)


def word(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def signed16(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def constant_sites(data, base, targets):
    """Adjacent LUI + ADDIU/ORI/load/store facts; no code/data claim."""
    result = []
    for offset in range(0, len(data) - 7, 4):
        high, low = struct.unpack_from("<II", data, offset)
        if high >> 26 != 15:
            continue
        register = (high >> 16) & 31
        if not register or (low >> 21) & 31 != register:
            continue
        opcode = low >> 26
        if opcode not in (9, 13, 32, 33, 35, 36, 37, 40, 41, 43):
            continue
        upper = (high & 0xFFFF) << 16
        address = (upper | (low & 0xFFFF)) if opcode == 13 else (
            upper + signed16(low)) & 0xFFFFFFFF
        labels = [name for name, begin, end in targets if begin <= address < end]
        if labels:
            result.append({
                "pc": f"0x{base + offset:08X}",
                "file_offset": offset,
                "words": [f"0x{high:08X}", f"0x{low:08X}"],
                "constant": f"0x{address:08X}", "regions": labels,
            })
    return result


def image_data(name, raw):
    if name.startswith("SCUS_"):
        if raw[:8] != b"PS-X EXE":
            raise ValueError("Invalid PS-X EXE header")
        return raw[0x800:], word(raw, 0x18)
    if name.endswith(".MNU"):
        return raw, 0x801D0000
    if name.endswith(".X"):
        if raw[8:11] != b"\x1f\x8b\x08":
            raise ValueError(f"Unsupported compressed overlay header: {name}")
        data = zlib.decompress(raw[8:], wbits=31)
        if len(data) != word(raw, 0):
            raise ValueError(f"Overlay decompressed-size mismatch: {name}")
        return data, 0x801B0000 if name.endswith("/BATINI.X") else 0x800A0000
    raise ValueError(f"Unsupported image: {name}")


def kernel_sections(raw):
    result, offset = [], 0
    for index in range(27):
        compressed, size, kind = struct.unpack_from("<HHH", raw, offset)
        begin = offset + 6
        data = zlib.decompress(raw[begin:begin + compressed], wbits=31)
        if len(data) != size:
            raise ValueError(f"Kernel section {index + 1} length mismatch")
        result.append(data)
        offset = begin + compressed
    if len(raw) != ((offset + 3) & ~3) or any(raw[offset:]):
        raise ValueError("Unexpected trailing kernel data")
    return result


def verify_evidence(disc, boot_name, evidence):
    if evidence.get("schema") != "ff7 expanded party research v1":
        raise ValueError("Unsupported party evidence schema")
    for name, spec in evidence["images"].items():
        actual_name = boot_name if name.startswith("SCUS_") else name
        raw = disc.read(actual_name)
        body, base = image_data(actual_name, raw)
        if hashlib.sha256(raw).hexdigest() != spec["sha256"] or (
            hashlib.sha256(body).hexdigest() != spec["decoded_sha256"]
        ) or base != int(spec["load_base"], 0):
            raise ValueError(f"Party evidence image mismatch: {actual_name}")
    for site in evidence["sites"]:
        name = boot_name if site["file"].startswith("SCUS_") else site["file"]
        body, base = image_data(name, disc.read(name))
        pc = int(site["pc"], 0)
        expected = tuple(int(value, 0) for value in site["words"])
        if pc < base or pc + 4 * len(expected) > base + len(body):
            raise ValueError(f"Party evidence site outside image: {name}/{site['pc']}")
        if struct.unpack_from(f"<{len(expected)}I", body, pc - base) != expected:
            raise ValueError(f"Party evidence instruction mismatch: {name}/{site['pc']}")
    return len(evidence["sites"])


def inspect(cue, evidence=None):
    symbols = tomllib.loads((ROOT / "symbols.toml").read_text(encoding="utf-8"))
    names = {entry["name"]: entry["pc"] for entry in symbols["func"]}
    disc = Disc(cue)
    try:
        boot_names = [name for name in disc.files if name.startswith("SCUS_")]
        if len(boot_names) != 1:
            raise ValueError("Expected one NTSC-U boot executable")
        exe = disc.read(boot_names[0])
        sha1 = hashlib.sha1(exe).hexdigest()
        if sha1 != EXE_SHA1:
            raise ValueError(f"Unsupported executable SHA-1: {sha1}")
        load = word(exe, 0x18)
        alias_address = names["g_BattleCharIdToCharId"]
        aliases = struct.unpack_from("<11I", exe, 0x800 + alias_address - load)
        if aliases != (0, 1, 2, 3, 4, 5, 6, 7, 8, 6, 7):
            raise ValueError("Unexpected character alias table")
        name_address = names["GetCharacterName"]
        routine = struct.unpack_from("<13I", exe, 0x800 + name_address - load)
        if routine != NAME_WORDS:
            raise ValueError("Unexpected character-name routine")
        save = names["Savemap"]
        targets = [
            ("character_aliases", alias_address, alias_address + 44),
            ("native_character_records", save + 0x54, save + 0x4F8),
            ("active_party", save + 0x4F8, save + 0x4FC),
            ("phs_masks", save + 0x10A4, save + 0x10A8),
        ]
        image_names = [boot_names[0]] + sorted(name for name in disc.files
            if name.endswith(".MNU") or name in (
                "BATTLE/BATINI.X", "BATTLE/BATTLE.X", "BATTLE/BROM.X"))
        images = []
        for name in image_names:
            raw = disc.read(name)
            body, base = image_data(name, raw)
            images.append({
                "file": name, "load_base": f"0x{base:08X}",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "decoded_sha256": hashlib.sha256(body).hexdigest(),
                "decoded_size": len(body),
                "candidate_constant_sites": constant_sites(body, base, targets),
            })
        portrait = "MENU/PCEFI.TIM"
        kernel = kernel_sections(disc.read("INIT/KERNEL.BIN"))
        default_ids = [kernel[3][132 * index] for index in range(9)]
        if default_ids != [0, 1, 2, 3, 4, 5, 9, 10, 8]:
            raise ValueError("Unexpected kernel initial character records")
        ai_offset = struct.unpack_from("<H", kernel[2], 0x61C + 10 * 2)[0]
        ai_script_offsets = struct.unpack_from("<16H", kernel[2], 0x61C + ai_offset)
        result = {
            "schema": "ff7 party storage audit v1",
            "cue": str(cue), "boot_executable": boot_names[0], "boot_sha1": sha1,
            "verified": {
                "alias_table_address": f"0x{alias_address:08X}",
                "alias_records": list(aliases),
                "name_lookup_address": f"0x{name_address:08X}",
                "name_lookup_words": [f"0x{value:08X}" for value in routine],
                "name_formula": "0x8009C748 + 132 * alias[guest_character_id]",
                "sephiroth_and_vincent_share_native_record": aliases[10] == aliases[7],
                "portrait_file_exists": portrait in disc.files,
                "kernel_initial_record_ids": default_ids,
                "kernel_initial_data_sha256": hashlib.sha256(kernel[3]).hexdigest(),
                "sephiroth_template_offset_in_initial_data": 7 * 132,
                "sephiroth_template_sha256": hashlib.sha256(kernel[3][7 * 132:8 * 132]).hexdigest(),
                "kernel_character_ai_table_offset": "0x061C",
                "sephiroth_ai_header_offset": f"0x{0x61C + ai_offset:04X}",
                "sephiroth_ai_script_offsets": list(ai_script_offsets),
                "battle_model_file": "ENEMY6/SEFIROS.LZS",
                "battle_model_sha256": hashlib.sha256(disc.read("ENEMY6/SEFIROS.LZS")).hexdigest(),
            },
            "candidate_regions": [dict(name=n, begin=f"0x{a:08X}", end=f"0x{b:08X}")
                                  for n, a, b in targets],
            "images": images,
            "limitations": [
                "Static observations only; no gameplay patch is enabled.",
                "Candidate references include data and need control-flow validation.",
                "Menu overlay load bases remain contextual; verify live loader traces.",
                "PHS enumeration, battle initialization and command/animation adapters are unimplemented.",
            ],
        }
        if evidence is not None:
            result["verified_evidence_sites"] = verify_evidence(disc, boot_names[0], evidence)
        return result
    finally:
        # Framework reader holds an open file; close it when the implementation
        # exposes close (the process also closes it on exit).
        close = getattr(disc.reader, "close", None)
        if close:
            close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cue", type=Path)
    parser.add_argument("--output", type=Path,
                        help="Optional metadata report; no original asset bytes are written")
    parser.add_argument("--verify-evidence", type=Path,
                        help="Recheck image hashes and instruction words in a saved party evidence file")
    args = parser.parse_args()
    try:
        evidence = json.loads(args.verify_evidence.read_text(encoding="utf-8")) if args.verify_evidence else None
        result = inspect(args.cue, evidence)
    except (ValueError, OSError, struct.error, zlib.error) as error:
        parser.exit(1, f"error: {error}\n")
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
