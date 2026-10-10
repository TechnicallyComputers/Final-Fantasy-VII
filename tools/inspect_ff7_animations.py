#!/usr/bin/env python3
"""Inspect original PSX FFVII party battle models without distributing assets.

Container facts are derived from the owner's disc and cross-checked against
original reverse-engineering reports. No decompilation source is read/imported.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import struct

from inspect_ff7_party import Disc, ROOT


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def decompress_lzs(raw, limit=2 * 1024 * 1024):
    """FFVII's bounded 4KiB-ring LZSS variant, with compressed-length header."""
    if len(raw) < 4 or u32(raw, 0) != len(raw) - 4:
        raise ValueError("LZS compressed-size header mismatch")
    ring = bytearray(4096)
    cursor, position, out = 4, 0xFEE, bytearray()
    while cursor < len(raw):
        flags = raw[cursor]
        cursor += 1
        if cursor == len(raw):
            raise ValueError("LZS flag byte without a token")
        for bit in range(8):
            if cursor == len(raw):
                break
            if flags & (1 << bit):
                source, count = None, 1
                literal = raw[cursor]
                cursor += 1
            else:
                if cursor + 2 > len(raw):
                    raise ValueError("Truncated LZS backreference")
                low, high = raw[cursor:cursor + 2]
                cursor += 2
                source = low | ((high & 0xF0) << 4)
                count = (high & 15) + 3
            if len(out) + count > limit:
                raise ValueError("LZS output exceeds configured limit")
            for _ in range(count):
                value = literal if source is None else ring[source]
                out.append(value)
                ring[position] = value
                position = (position + 1) & 4095
                if source is not None:
                    source = (source + 1) & 4095
    return bytes(out)


def sections(data):
    if len(data) < 12:
        raise ValueError("Truncated battle model header")
    count = u32(data, 0)
    if not 3 <= count <= 256 or 4 + count * 4 > len(data):
        raise ValueError("Invalid battle model section count")
    offsets = list(struct.unpack_from(f"<{count}I", data, 4))
    if offsets[0] != 4 + count * 4:
        raise ValueError("Battle model first section does not follow its offset table")
    if any(a >= b or a % 4 for a, b in zip(offsets, offsets[1:] + [len(data)])):
        raise ValueError("Invalid battle model section extents")
    return [data[a:b] for a, b in zip(offsets, offsets[1:] + [len(data)])], offsets


def pack_sections(chunks):
    offsets, cursor = [], 4 + len(chunks) * 4
    for chunk in chunks:
        if not chunk or len(chunk) % 4:
            raise ValueError("Battle model sections must be nonempty and aligned")
        offsets.append(cursor)
        cursor += len(chunk)
    return struct.pack(f"<{len(chunks) + 1}I", len(chunks), *offsets) + b"".join(chunks)


def literal_lzs(data):
    """Simple lossless owner-local packaging, not an optimized compressor."""
    encoded = bytearray()
    for offset in range(0, len(data), 8):
        part = data[offset:offset + 8]
        encoded.append((1 << len(part)) - 1)
        encoded.extend(part)
    return struct.pack("<I", len(encoded)) + encoded


OPERANDS = {
    0x90: 3, 0x91: 1, 0x94: 5, 0x96: 2, 0x97: 2, 0x98: 1,
    0x99: 6, 0x9A: 4, 0x9D: 1, 0xA0: 1, 0xA1: 2, 0xA2: 1,
    0xA3: 1, 0xA7: 1, 0xA8: 2, 0xAB: 4, 0xAC: 1, 0xAD: 5,
    0xAF: 1, 0xB5: 11, 0xB6: 1, 0xB9: 1, 0xBA: 2, 0xBC: 1,
    0xBD: 4, 0xBE: 1, 0xBF: 2, 0xC2: 1, 0xC4: 3, 0xC6: 1,
    0xC7: 3, 0xC8: 5, 0xCB: 8, 0xCC: 1, 0xCE: 1, 0xCF: 8,
    0xD0: 3, 0xD1: 5, 0xD4: 3, 0xD5: 8, 0xD6: 1, 0xD7: 2,
    0xD8: 3, 0xDA: 1, 0xDB: 4, 0xDC: 3, 0xDD: 2, 0xDE: 2,
    0xE7: 1, 0xE9: 3, 0xF4: 1, 0xF5: 1, 0xF7: 1, 0xF8: 1,
    0xFB: 4, 0xFD: 6, 0xFE: 1,
}
# These bytes have no ordinary opcode implementation in the documented VM.
DUMMY = {0xBB, 0xC0, 0xCD, 0xD2, 0xD3, 0xD9, 0xEF}
BODY_SLOTS = 52
NULL_MOTION = bytes.fromhex("301a0000")
MODELS = {"cloud": "CLOUD", "vincent": "VINSENT", "sephiroth": "SEFIROS"}
SEPHIROTH_SHA256 = "7e3a94d9b338c5038c947c77669699ddf19d6f0466008a9bfabd158cc819b785"
SOURCES = [
    "https://wiki.ffrtt.ru/index.php/FF7/Playstation_Battle_Model_Format",
    "https://forums.qhimm.com/index.php?topic=14200.0",
    "https://ff7-mods.github.io/ff7-flat-wiki/FF7/Battle/Battle_Animation/Animation_Script.html",
    "https://wiki.ffrtt.ru/index.php/FF7/Battle/Battle_Animation_(PC)",
    "https://forums.qhimm.com/index.php?topic=19266.0",
]
# Action roles are documented research labels, not inferred from raw motion IDs.
# Defend has no verified action ID yet; do not give a guessed slot that patches
# another command. Limit dispatch also requires external effect/asset tracing.
ROLES = {
    "idle": [0x00], "near_death": [0x01], "death": [0x02],
    "damage_reactions": [0x05, 0x06, 0x07], "evade": [0x08],
    "cover": [0x09], "victory": [0x0C], "run": [0x0D, 0x0E],
    "attack": [0x14], "slash_all": [0x15], "double_cut": [0x16, 0x17],
    "four_cut": [0x18, 0x19, 0x1A, 0x1B], "flash": [0x1C],
    "magic": [0x1D], "enemy_skill": [0x1E], "summon": [0x1F],
    "item_variants": [0x20, 0x21],
}


class Bits:
    def __init__(self, data):
        self.data, self.position = data, 0

    def read(self, count, signed=False):
        if count < 1 or self.position + count > len(self.data) * 8:
            raise ValueError("Motion bitstream is truncated")
        value = 0
        for _ in range(count):
            value = (value << 1) | ((self.data[self.position // 8] >>
                                    (7 - self.position % 8)) & 1)
            self.position += 1
        return value - (1 << count) if signed and value & (1 << (count - 1)) else value


def motion(data, rotations):
    """Validate/decode an entire PSX motion; return metadata, not animation data.

    The miniature header/bit encoding is shared with the PC research format;
    its applicability to each PSX motion is checked, never presumed. The root
    adds one rotation triple to body bone count; weapon motions have one.
    """
    if data == NULL_MOTION:
        return {"kind": "placeholder", "bytes": 4}
    if len(data) < 5:
        raise ValueError("Truncated motion header")
    frames, size, key = struct.unpack_from("<HHB", data)
    if not frames or frames > 4096 or key not in (0, 2, 4):
        raise ValueError("Invalid motion frame count or precision key")
    if not 1 <= rotations <= 256 or not 0 <= len(data) - 5 - size <= 3:
        raise ValueError("Invalid motion payload extent or skeleton size")
    if any(data[5 + size:]):
        raise ValueError("Nonzero motion alignment padding")
    bits = Bits(data[5:5 + size])
    position = [bits.read(16, True) for _ in range(3)]
    angles = [(bits.read(12 - key, True) << key) & 4095
              for _ in range(rotations * 3)]
    minima, maxima = position.copy(), position.copy()
    for _ in range(frames - 1):
        for axis in range(3):
            width = 16 if bits.read(1) else 7
            value = (position[axis] + bits.read(width, True)) & 65535
            position[axis] = value - 65536 if value & 32768 else value
            minima[axis] = min(minima[axis], position[axis])
            maxima[axis] = max(maxima[axis], position[axis])
        for index in range(len(angles)):
            if not bits.read(1):
                continue
            width = bits.read(3)
            if width == 0:
                delta = -1
            elif width == 7:
                delta = bits.read(12 - key, True)
            else:
                delta = bits.read(width, True)
                delta += -(1 << (width - 1)) if delta < 0 else 1 << (width - 1)
            angles[index] = (angles[index] + (delta << key)) & 4095
    unused = size * 8 - bits.position
    # Header frame counts occasionally disagree with payload size in the PC
    # format. Report leftover bytes explicitly instead of certifying a writer.
    return {"kind": "motion", "bytes": len(data), "frames": frames,
            "key": key, "rotations": rotations, "payload_bytes": size,
            "consumed_bits": bits.position, "unused_bits": unused,
            "position_min": minima, "position_max": maxima}


def script(data):
    """Bounded static action walk, with operands and reachable alternatives.

    This is not a battle VM. Conditional B3 branches are conservatively joined;
    asynchronous effects are recorded, not executed. Bytes after an ordinary
    terminator (including unreferenced routines and alignment) are ignored.
    """
    cursor, refs, opcodes, issues, pending = 0, set(), set(), [], []
    visited = set()
    terminated = False
    while cursor < len(data):
        if cursor in visited:
            if pending:
                cursor = pending.pop()
                continue
            break
        visited.add(cursor)
        opcode = data[cursor]
        cursor += 1
        if opcode < 0x8E:
            refs.add(opcode)
            continue
        opcodes.add(opcode)
        if opcode in DUMMY:
            issues.append(f"unimplemented_opcode_{opcode:02x}")
            break
        if opcode == 0xA9:
            if cursor + 2 > len(data):
                issues.append("truncated_A9")
                break
            if data[cursor + 1] >= 0x8E:
                issues.append("A9_non_motion_operand")
                break
            refs.add(data[cursor + 1])
            cursor += 2
            continue
        length = OPERANDS.get(opcode, 0)
        if cursor + length > len(data):
            issues.append(f"truncated_operand_{opcode:02x}")
            break
        args = data[cursor:cursor + length]
        cursor += length
        if opcode in (0xB6, 0xDA):
            refs.add(args[0])
        if opcode == 0xB3:
            # The engine's skip searches for byte B2, rather than decoding a
            # nested language. Include both paths, even after the first EE.
            target = data.find(b"\xb2", cursor)
            if target < 0:
                issues.append("B3_without_B2")
            else:
                pending.append(target + 1)
        if opcode == 0xC1:
            target = data.find(b"\xc9")
            if target < 0:
                issues.append("C1_without_C9")
                break
            cursor = target + 1
        if opcode in (0xEE, 0xFF, 0xF1) or opcode == 0xFE and args[0] == 0xC0:
            terminated = True
            if pending:
                cursor = pending.pop()
            else:
                break
    if not terminated and not issues:
        issues.append("fragment_without_idle_or_end")
    return {"motion_ids": sorted(refs), "opcodes": sorted(opcodes),
            "issues": issues, "effect_dispatch": 0xEC in opcodes,
            "transformation": bool({0xAC, 0xA2} & opcodes)}


def actions(settings):
    if len(settings) < 108:
        raise ValueError("Truncated model settings")
    first = u32(settings, 0x68)
    if first < 108 or first % 4 or first > len(settings):
        raise ValueError("Invalid action table extent")
    count = (first - 0x68) // 4
    if count != 74:
        raise ValueError("Unsupported action table: expected 74 player actions")
    pointers = list(struct.unpack_from(f"<{count}I", settings, 0x68))
    valid = sorted({p for p in pointers if first <= p < len(settings)})
    ends = dict(zip(valid, valid[1:] + [len(settings)]))
    result = []
    for index, pointer in enumerate(pointers):
        entry = {"id": index, "settings_offset": pointer}
        if pointer not in ends:
            entry.update({"kind": "unavailable", "motion_ids": [],
                          "issues": ["pointer_outside_script_area"]})
        else:
            entry.update(script(settings[pointer:ends[pointer]]))
            entry["kind"] = "script"
        result.append(entry)
    return result


def tim(data):
    if len(data) < 20 or u32(data, 0) != 16 or u32(data, 4) & ~15:
        return False
    flags, offset = u32(data, 4), 8
    for _ in range(2 if flags & 8 else 1):
        if offset + 12 > len(data):
            return False
        length = u32(data, offset)
        width, height = struct.unpack_from("<HH", data, offset + 8)
        if length != 12 + width * height * 2 or offset + length > len(data):
            return False
        offset += length
    return offset == len(data)


def model_inventory(raw):
    unpacked = decompress_lzs(raw)
    chunks, offsets = sections(unpacked)
    texture = next((i for i in range(2, len(chunks)) if tim(chunks[i])), None)
    if texture is None or texture < 2 + BODY_SLOTS:
        raise ValueError("Missing expected player TIM/motion banks")
    bones = u32(chunks[0], 0)
    motions = []
    for index, chunk in enumerate(chunks[2:texture]):
        entry = {"id": index, "section": index + 2,
                 "file_offset": offsets[index + 2],
                 "bank": "body" if index < BODY_SLOTS else "weapon"}
        try:
            entry.update(motion(chunk, bones + 1 if index < BODY_SLOTS else 1))
        except ValueError as error:
            entry.update({"kind": "invalid", "bytes": len(chunk), "error": str(error)})
        motions.append(entry)
    action_list = actions(chunks[1])
    for entry in action_list:
        refs = entry["motion_ids"]
        entry["unresolved_body_motion_ids"] = [
            i for i in refs if i >= BODY_SLOTS or motions[i]["kind"] != "motion"]
        entry["idle_only"] = entry["kind"] == "script" and refs == [0]
    paired = []
    for index in range(BODY_SLOTS, len(motions)):
        weapon, body = motions[index], motions[index - BODY_SLOTS]
        if weapon["kind"] != body["kind"] or weapon.get("frames") != body.get("frames"):
            paired.append(index - BODY_SLOTS)
    return {"sha256": hashlib.sha256(raw).hexdigest(),
            "decoded_sha256": hashlib.sha256(unpacked).hexdigest(),
            "compressed_bytes": len(raw), "decoded_bytes": len(unpacked),
            "section_count": len(chunks), "skeleton_bones": bones,
            "skeleton_sha256": hashlib.sha256(chunks[0]).hexdigest(),
            "settings_bytes": len(chunks[1]), "texture_section": texture,
            "weapon_model_sections": len(chunks) - texture - 1,
            "body_motion_count": sum(m["kind"] == "motion" for m in motions[:BODY_SLOTS]),
            "body_placeholders": [m["id"] for m in motions[:BODY_SLOTS] if m["kind"] == "placeholder"],
            "motion_validation_errors": [m["id"] for m in motions if m["kind"] == "invalid"],
            "body_weapon_frame_mismatches": paired,
            "motions": motions, "actions": action_list,
            "roles": {name: [{"action_id": i,
                               "motion_ids": action_list[i]["motion_ids"],
                               "unresolved_body_motion_ids": action_list[i]["unresolved_body_motion_ids"],
                               "idle_only": action_list[i]["idle_only"]}
                              for i in ids] for name, ids in ROLES.items()}}


@contextmanager
def owner_disc(cue):
    disc = Disc(Path(cue))
    try:
        yield disc
    finally:
        disc.reader.close()


def inspect(cue):
    models = {}
    with owner_disc(cue) as disc:
        for name, basename in MODELS.items():
            candidates = [path for path in disc.files if path.endswith("/" + basename + ".LZS")]
            if len(candidates) != 1:
                raise ValueError(f"Expected one {basename}.LZS on disc, found {candidates}")
            models[name] = {"disc_path": candidates[0], **model_inventory(disc.read(candidates[0]))}
    return {"schema": 1, "status": "developer-only-static-inventory",
            "sources": SOURCES, "body_motion_slots": BODY_SLOTS,
            "models": models,
            "limitations": [
                "Static scripts do not prove command dispatch or visual correctness.",
                "Some limit motions are supplied dynamically; a placeholder is not proof a limit is broken.",
                "Defend dispatch and limit effect/model replacement still require binary tracing.",
                "Equal bone counts do not establish compatible hierarchy, bind pose, or skinning.",
                "No animations, scripts, game assets, or guest memory are modified.",
                "No full controllable-party animation set has been implemented or validated.",
            ]}


def fallback_candidate(raw):
    """Prepare review-only motions from Sephiroth's own skeleton and motions.

    This fills cover/items with existing evade/casting gestures and changes
    idle damage reactions to his evade gesture. It does not author death,
    defend, or limits, and is deliberately not installed into the game.
    """
    if hashlib.sha256(raw).hexdigest() != SEPHIROTH_SHA256:
        raise ValueError("Unverified Sephiroth source hash; refusing candidate preparation")
    original = model_inventory(raw)
    if original["skeleton_bones"] != 47 or original["body_motion_count"] != 17:
        raise ValueError("Unexpected Sephiroth model; refusing candidate preparation")
    chunks, _ = sections(decompress_lzs(raw))
    before = chunks.copy()
    substitutions = {8: 5, 9: 12, 10: 12}
    for target, source in substitutions.items():
        for bank in (0, BODY_SLOTS):
            destination, origin = 2 + bank + target, 2 + bank + source
            if chunks[destination] != NULL_MOTION or chunks[origin] == NULL_MOTION:
                raise ValueError("Unexpected fallback motion source/destination")
            chunks[destination] = chunks[origin]
    settings = bytearray(chunks[1])
    changed_offsets = set()
    # Guard original bytes before editing. Multiple actions can intentionally
    # share the same source script; reject any alias from outside this set.
    damage = {5: b"\x00\xf2\xe5\xee", 6: b"\x00\x00\xf2\xe5\xee",
              7: b"\x00\xf2\xe5\xee"}
    pointers = [a["settings_offset"] for a in original["actions"]]
    for action, expected in damage.items():
        pointer = pointers[action]
        if set(i for i, p in enumerate(pointers) if p == pointer) - damage.keys():
            raise ValueError("Damage script aliases an unrelated action")
        if before[1][pointer:pointer + len(expected)] != expected:
            raise ValueError("Unexpected Sephiroth damage script")
        for offset, value in enumerate(expected):
            if value == 0:
                settings[pointer + offset] = 5
                changed_offsets.add(pointer + offset)
    chunks[1] = bytes(settings)
    packed = pack_sections(chunks)
    encoded = literal_lzs(packed)
    if decompress_lzs(encoded) != packed:
        raise ValueError("Prepared LZS failed byte-exact round trip")
    after = model_inventory(encoded)
    if after["motion_validation_errors"] or after["body_weapon_frame_mismatches"]:
        raise ValueError("Prepared body/weapon motions failed validation")
    if any(m.get("unused_bits", 0) > 7 for m in after["motions"]):
        raise ValueError("Prepared motion has unexplained payload bytes")
    expected_sections = {1} | {2 + bank + target for bank in (0, BODY_SLOTS)
                              for target in substitutions}
    if {i for i, (a, b) in enumerate(zip(before, chunks)) if a != b} != expected_sections:
        raise ValueError("Unexpected section changed during preparation")
    for role in ("cover", "item_variants", "damage_reactions"):
        if any(a["unresolved_body_motion_ids"] or a["idle_only"] for a in after["roles"][role]):
            raise ValueError("Prepared role still references a missing/idle motion")
    return encoded, {
        "status": "developer-only-needs-visual-and-runtime-review",
        "source_sha256": original["sha256"], "candidate_sha256": after["sha256"],
        "source_bytes": len(raw), "candidate_bytes": len(encoded),
        "body_motion_substitutions": {str(k): v for k, v in substitutions.items()},
        "weapon_motion_substitutions": {str(k): v for k, v in substitutions.items()},
        "damage_actions": sorted(damage), "settings_bytes_changed": sorted(changed_offsets),
        "skeleton_preserved": before[0] == chunks[0],
        "body_motion_count": after["body_motion_count"],
        "limitations": [
            "Existing evade gesture substitutes for cover and damage; existing casting gesture substitutes for items.",
            "No new artistic animation is claimed. Death, near-death, defend, limits and multihit completeness remain unresolved.",
            "Frame/bitstream validation does not prove animation timing, position, collision, or visual quality in battle.",
            "Literal LZS is larger than the source. Guest loader allocation limits must be checked before integration.",
            "Do not replace the stock model globally: the flashback actor must retain its original behavior.",
            "This candidate is not installed, enabled, or shipped by the mod.",
        ],
    }


def prepare(cue, directory):
    destination = Path(directory).resolve()
    allowed = [(ROOT / name).resolve() for name in ("analysis", "disc")]
    if not any(destination.is_relative_to(root) and destination != root for root in allowed):
        raise ValueError("Prepared game assets must stay under an ignored analysis/ or disc/ subdirectory")
    for name in ("SEFIROS.LZS", "preparation.json"):
        if (destination / name).is_symlink() or (destination / name).resolve().parent != destination:
            raise ValueError("Prepared asset output must not follow a link outside its directory")
    with owner_disc(cue) as disc:
        raw = disc.read("ENEMY6/SEFIROS.LZS")
    encoded, report = fallback_candidate(raw)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "SEFIROS.LZS").write_bytes(encoded)
    (destination / "preparation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cue", type=Path)
    parser.add_argument("--output", type=Path, help="Write metadata JSON (contains no extracted assets)")
    parser.add_argument("--prepare-fallbacks", type=Path,
                        help="Prepare review-only owner-local Sephiroth fallbacks under ignored analysis/ or disc/")
    args = parser.parse_args()
    result = inspect(args.cue)
    if args.prepare_fallbacks:
        result["candidate_preparation"] = prepare(args.cue, args.prepare_fallbacks)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
