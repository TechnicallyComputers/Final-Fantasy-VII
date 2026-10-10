#!/usr/bin/env python3
"""Inspect/export FFVII raw 128KiB cards and versioned appended extensions.

No game-specific save fields are rewritten. Export preserves the standard base
byte for byte and omits expanded-party metadata. See SEPHIROTH_SAVE_FORMAT.md.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import zlib

CARD_SIZE = 131072
HEADER = 64
MEMBER_SIZE = 136
MAX_MEMBERS = 16
PAYLOAD_HEADER = 80
MAX_PAYLOAD = PAYLOAD_HEADER + MAX_MEMBERS * MEMBER_SIZE
MAX_EXTENSION = HEADER + 15 * (8 + MAX_PAYLOAD)
MAX_FILE = CARD_SIZE + MAX_EXTENSION
EMPTY = 0xFFFF


class SaveFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Member:
    id: int
    presentation_id: int
    flags: int
    record: bytes


@dataclass(frozen=True)
class Party:
    active: tuple[int, int, int]
    members: tuple[Member, ...]
    stored: tuple[int, int, int] = (EMPTY, EMPTY, EMPTY)
    stored_hint: tuple[int, int, int] = (255, 255, 255)
    stored_known: bool = False


@dataclass(frozen=True)
class Card:
    base: bytes
    slots: dict[int, Party]
    extended: bool
    binding_matches: bool = True


def require(condition, message):
    if not condition:
        raise SaveFormatError(message)


def crc(data):
    return zlib.crc32(data[:60] + bytes(4) + data[64:]) & 0xFFFFFFFF


def frame_valid(frame):
    value = 0
    for byte in frame:
        value ^= byte
    return len(frame) == 128 and value == 0


def validate_base(base):
    require(len(base) == CARD_SIZE, "Only raw 128KiB memory cards are supported")
    require(base[:2] == b"MC", "Missing raw memory-card MC signature")
    require(frame_valid(base[:128]), "Memory-card header XOR checksum is invalid")


def validate_slot(base, slot):
    require(1 <= slot <= 15, "Directory slot must be 1..15")
    frame = base[slot * 128:(slot + 1) * 128]
    require(struct.unpack_from("<I", frame)[0] == 0x51 and frame_valid(frame),
            f"Slot {slot} is not a valid allocated first directory frame")


def validate_party(party):
    require(len(party.members) <= MAX_MEMBERS, "Expanded member count exceeds 16")
    members = {}
    for member in party.members:
        require(0x100 <= member.id < EMPTY and member.id not in members,
                "Invalid or duplicate expanded member identity")
        require(0 <= member.presentation_id <= 10 and member.flags in (0, 1),
                "Invalid presentation identity or member flags")
        require(len(member.record) == 132, "Character record must contain exactly 132 bytes")
        members[member.id] = member
    require(party.stored_known in (False, True), "Invalid stored-party presence flag")
    for roster in (party.active, party.stored):
        require(len(roster) == 3, "Party must contain three slots")
        present = []
        for identity in roster:
            if identity == EMPTY:
                continue
            require(0 <= identity < 9 or identity in members and members[identity].flags & 1,
                    "Identity is neither native nor an unlocked expanded member")
            require(identity not in present, "Duplicate party identity")
            present.append(identity)
    require(party.stored_known or party.stored == (EMPTY, EMPTY, EMPTY), "Unknown stored party contains members")
    require(len(party.stored_hint) == 3, "Stored hints must contain three entries")
    for identity, hint in zip(party.stored, party.stored_hint):
        require(hint == 255 or party.stored_known and (identity, hint) in ((6, 9), (7, 10)),
                "Invalid stored native alias hint")


def encode_payload(party, digest):
    validate_party(party)
    require(len(digest) == 32, "Expected SHA256 of the complete base card")
    out = bytearray(PAYLOAD_HEADER + len(party.members) * MEMBER_SIZE)
    out[:8] = b"FF7PARTY"
    struct.pack_into("<HHIH3H", out, 8, 3, PAYLOAD_HEADER, len(out), len(party.members), *party.active)
    out[24:56] = digest
    struct.pack_into('<3H3BB', out, 64, *party.stored, *party.stored_hint, party.stored_known)
    for index, member in enumerate(party.members):
        offset = PAYLOAD_HEADER + index * MEMBER_SIZE
        struct.pack_into("<HBB", out, offset, member.id, member.presentation_id, member.flags)
        out[offset + 4:offset + MEMBER_SIZE] = member.record
    struct.pack_into("<I", out, 60, crc(out))
    return bytes(out)


def decode_payload(data, digest):
    require(HEADER <= len(data) <= MAX_PAYLOAD and data[:8] == b"FF7PARTY", "Invalid party payload")
    version, header, size, count, *active = struct.unpack_from("<HHIH3H", data, 8)
    require(version in (2, 3), "Unsupported party payload version (v1 sidecars are not full-card bound)")
    expected_header = HEADER if version == 2 else PAYLOAD_HEADER
    require(header == expected_header and size == len(data) and len(data) >= header and data[56:60] == bytes(4), "Invalid payload header")
    require(struct.unpack_from("<I", data, 60)[0] == crc(data), "Party payload CRC32 mismatch")
    require(data[24:56] == digest, "Party payload does not match the complete base card")
    require(count <= MAX_MEMBERS and len(data) == header + count * MEMBER_SIZE, "Invalid payload member count/extent")
    members = []
    for offset in range(header, len(data), MEMBER_SIZE):
        identity, presentation, flags = struct.unpack_from("<HBB", data, offset)
        members.append(Member(identity, presentation, flags, data[offset + 4:offset + MEMBER_SIZE]))
    party = Party(tuple(active), tuple(members))
    if version == 3:
        require(data[74:80] == bytes(6), 'Nonzero reserved payload bytes')
        party = Party(tuple(active), tuple(members), struct.unpack_from('<3H', data, 64),
                      tuple(data[70:73]), data[73])
    validate_party(party)
    return party


def encode_extension(base, slots):
    validate_base(base)
    require(len(slots) <= 15, "At most 15 directory-slot entries are supported")
    digest = hashlib.sha256(base).digest()
    out = bytearray(HEADER)
    for slot, party in sorted(slots.items()):
        validate_slot(base, slot)
        payload = encode_payload(party, digest)
        out += struct.pack("<B3xI", slot, len(payload)) + payload
    out[:8] = b"FF7MCEXT"
    struct.pack_into("<HHIHHI", out, 8, 1, HEADER, len(out), len(slots), 0, CARD_SIZE)
    out[24:56] = digest
    struct.pack_into("<I", out, 60, crc(out))
    return bytes(out)


def parse_card(data, *, recover_base=False):
    require(CARD_SIZE <= len(data) <= MAX_FILE, "Unsupported/truncated memory-card file size")
    base, tail = data[:CARD_SIZE], data[CARD_SIZE:]
    validate_base(base)
    if not tail:
        return Card(base, {}, False)
    require(HEADER <= len(tail) <= MAX_EXTENSION and tail[:8] == b"FF7MCEXT", "Unknown or truncated appended data")
    version, header, size, count, flags, base_size = struct.unpack_from("<HHIHHI", tail, 8)
    require(version == 1, "Unsupported FF7MCEXT version")
    require(header == HEADER and size == len(tail) and count <= 15 and not flags and
            base_size == CARD_SIZE and tail[56:60] == bytes(4), "Invalid extension header")
    require(struct.unpack_from("<I", tail, 60)[0] == crc(tail), "Extension CRC32 mismatch")
    digest = hashlib.sha256(base).digest()
    binding_matches = tail[24:56] == digest
    require(binding_matches or recover_base, "Extension does not match the complete base card")
    # Explicit recovery permits ONLY a stale whole-card binding. Nested hashes
    # must still agree with the envelope and every structural/CRC check applies.
    payload_digest = digest if binding_matches else tail[24:56]
    slots, cursor, previous = {}, HEADER, 0
    for _ in range(count):
        require(len(tail) - cursor >= 8, "Truncated directory-slot entry")
        slot, payload_size = struct.unpack_from("<B3xI", tail, cursor)
        require(tail[cursor + 1:cursor + 4] == bytes(3) and slot > previous,
                "Nonzero entry flags or duplicate/unsorted directory slots")
        validate_slot(base, slot)
        cursor += 8
        require(HEADER <= payload_size <= MAX_PAYLOAD and payload_size <= len(tail) - cursor,
                "Invalid or truncated party payload extent")
        slots[slot] = decode_payload(tail[cursor:cursor + payload_size], payload_digest)
        previous, cursor = slot, cursor + payload_size
    require(cursor == len(tail), "Trailing bytes after extension entries")
    return Card(base, slots, True, binding_matches)


def read_card(path, *, recover_base=False):
    with Path(path).open("rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Input must be a regular file")
        # Bound the read, including one overflow byte, before parsing anything.
        return parse_card(stream.read(MAX_FILE + 1), recover_base=recover_base)


def atomic_create(path, data):
    """Publish a complete new file atomically; never replace an existing path.

    A same-directory temporary file is flushed then hard-linked exclusively to
    the requested path. Unsupported hard-link filesystems fail without a
    non-atomic fallback. The temporary name is removed in all ordinary failures.
    """
    destination = Path(path).absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"Output already exists: {destination}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".ff7-export-", suffix=".tmp",
                                         dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def describe(card):
    return {"format": "FF7MCEXT-v1" if card.extended else "raw-128KiB-MC",
            "standard_bytes": CARD_SIZE, "base_sha256": hashlib.sha256(card.base).hexdigest(),
            "binding_matches": card.binding_matches,
            "recovered_stale_binding": not card.binding_matches,
            "directory_slots": [{"slot": slot, "active_ids": list(party.active),
                                  "stored_ids": list(party.stored) if party.stored_known else None,
                                  "expanded_ids": [m.id for m in party.members],
                                  "active_extra_ids": [i for i in party.active if 0x100 <= i < EMPTY]}
                                 for slot, party in sorted(card.slots.items())],
            "export_policy": "Exact base bytes; expanded metadata is omitted. Native fallback party is unchanged."}


def export_standard(source, destination, *, recover_base=False):
    source, destination = Path(source), Path(destination)
    require(source.resolve() != destination.resolve(), "Input and output must be different paths")
    card = read_card(source, recover_base=recover_base)
    atomic_create(destination, card.base)
    return describe(card)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "export-standard"):
        child = commands.add_parser(command)
        child.add_argument("input", type=Path)
        if command == "export-standard":
            child.add_argument("--output", type=Path, required=True)
            child.add_argument("--recover-base", action="store_true",
                               help="Explicitly discard a structurally valid extension with stale base binding; other errors still fail")
    args = parser.parse_args()
    try:
        report = (describe(read_card(args.input)) if args.command == "inspect" else
                  export_standard(args.input, args.output, recover_base=args.recover_base))
    except (OSError, SaveFormatError) as error:
        parser.exit(2, f"ff7_save: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
