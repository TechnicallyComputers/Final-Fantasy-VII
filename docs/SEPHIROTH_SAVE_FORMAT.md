# Sephiroth and expanded-party save format

The specified persistence format stores expanded-party metadata **in the memory-card file**,
after the standard 128 KiB card image. It does not require a separate sidecar.
The first 131,072 bytes retain the standard card representation. Exporting a
standard card copies those bytes exactly and removes the extension.

This document specifies `FF7MCEXT` version 1 and its nested `FF7PARTY` version 2
payloads. The format codecs and export tool are implemented and tested. The
codecs alone do not make Sephiroth playable or integrate game save/load hooks.
The developer-only `party-save` feature now supplies a runtime adapter through
the shared memory-card extension transport. It loads and refreshes **existing**
validated metadata. It does not create metadata from gameplay or prove that a
native fallback party has been written into a particular real FFVII save.
The framework transport and title adapter build together in the runtime; a
separate integration test exercises their actual file writer on synthetic cards.
The exporter currently runs as a standalone command. Game save/load integration and rewind synchronization remain
unfinished; the lifecycle and fallback requirements below still apply.

## Supported files and original card structure

Only a raw **131,072-byte PlayStation memory-card image**, optionally followed
by this extension, is supported. `.mcd` is the intended filename extension;
the file contents determine validity. Headered emulator formats, single-save
`.mcs` files, compressed cards, PS2 cards, and concatenated cards are unsupported.

The card begins with ASCII `MC`. Its first 128-byte frame ends with the XOR of
the preceding 127 bytes. The card contains sixteen 8 KiB blocks. Block zero
holds the directory; frames 1–15 identify the fifteen file blocks. An allocated
file's first directory frame starts with little-endian `0x00000051`, and each
directory frame has its own XOR checksum. These structural facts follow the
[PSX-SPX memory-card format documentation](https://psx-spx.consoledev.net/controllersandmemorycards/#memory-card-data-format).

The codecs check the base size, `MC` signature, and header-frame XOR. For each
extension entry, they also check that its referenced directory frame has
allocation state `0x51` and a valid XOR. They do **not** certify all directory
chains, individual game's save checksums, filenames, or playable game state.
The gameplay adapter must establish that an entry belongs to the intended
FFVII save before associating party metadata with it.

## File layout and limits

All integer fields in the extension and payload are unsigned little-endian.
Hashes are raw 32-byte SHA-256 values, not text. Reserved bytes must be zero.

| Absolute offset | Length | Contents |
| --- | ---: | --- |
| `0x00000` | `0x20000` / 131,072 | Exact standard raw card bytes |
| `0x20000` | 64 or more | Optional `FF7MCEXT` extension |

Exactly 131,072 bytes means a standard card with no expanded-party metadata.
Any additional bytes must form one complete, supported extension. There is
no padding, repeated extension, trailing footer, or unvalidated extra data.

There can be 0–15 extension entries, one per **first allocated directory
frame**. This is the physical memory-card directory index, not a battle-party
position or a host array index. Entries must be strictly increasing by index;
duplicate entries are invalid. Each save entry can hold at most sixteen extra
characters. The maximum tail is 33,784 bytes (`0x83F8`), so the maximum complete
file is 164,856 bytes (`0x283F8`).

An empty extension is 64 bytes. One save entry containing one extra character
uses a 272-byte tail, for a total file size of 131,344 bytes (`0x20110`).

## Extension header: `FF7MCEXT` version 1

Offsets in this table are relative to absolute file offset `0x20000`.

| Offset | Bytes | Field |
| --- | ---: | --- |
| `0x00` | 8 | ASCII `FF7MCEXT` |
| `0x08` | 2 | Envelope version: `1` |
| `0x0A` | 2 | Header size: `64` |
| `0x0C` | 4 | Entire extension size, including this header |
| `0x10` | 2 | Save-entry count, `0..15` |
| `0x12` | 2 | Reserved flags: zero |
| `0x14` | 4 | Base-card size: `131072` |
| `0x18` | 32 | SHA-256 of the complete first 131,072 bytes |
| `0x38` | 4 | Reserved: zero |
| `0x3C` | 4 | CRC32 of the complete extension, with these four bytes zeroed |
| `0x40` | variable | Entries in ascending directory-index order |

The CRC uses reflected polynomial `0xEDB88320`, initial value `0xFFFFFFFF`,
and final XOR `0xFFFFFFFF`, equivalent to Python `zlib.crc32`. SHA-256 binds
metadata to the **entire card**, including unrelated saves and unused bytes.
Any base change requires re-encoding every payload and the envelope. CRC and
SHA-256 detect corruption and mismatched files; neither authenticates an
untrusted author who can recompute them.

## Per-save entry

The first entry starts at extension offset `0x40`. Each subsequent entry starts
immediately after the previous entry's payload.

| Entry-relative offset | Bytes | Field |
| --- | ---: | --- |
| `0x00` | 1 | First allocated directory-frame index, `1..15` |
| `0x01` | 3 | Reserved: zero |
| `0x04` | 4 | Payload byte count, `64..2240` |
| `0x08` | variable | One complete `FF7PARTY` version 2 payload |

A directory index is only meaningful together with the bound card image.
Deleting or replacing a save must remove its old metadata before rebinding.
Moving a save requires explicitly moving its metadata to the new directory
index. A matching index in a different file is not sufficient evidence that
the metadata belongs to the same save.

## Party payload: `FF7PARTY` version 2

| Payload-relative offset | Bytes | Field |
| --- | ---: | --- |
| `0x00` | 8 | ASCII `FF7PARTY` |
| `0x08` | 2 | Payload version: `2` |
| `0x0A` | 2 | Header size: `64` |
| `0x0C` | 4 | Payload size: `64 + 136 × member_count` |
| `0x10` | 2 | Extra-member count, `0..16` |
| `0x12` | 6 | Three active identities, each a 16-bit integer |
| `0x18` | 32 | SHA-256 of the same entire 131,072-byte base card |
| `0x38` | 4 | Reserved: zero |
| `0x3C` | 4 | CRC32 of this payload, with these four bytes zeroed |
| `0x40` | variable | Extra-member records |

Each 136-byte extra-member record contains:

| Record-relative offset | Bytes | Field |
| --- | ---: | --- |
| `0x00` | 2 | Independent identity, `0x0100..0xFFFE` |
| `0x02` | 1 | Presentation/asset identity, `0..10` |
| `0x03` | 1 | Flags: bit 0 means unlocked; all other bits must be zero |
| `0x04` | 132 | Opaque FFVII-format character record |

Extra identities must be unique. Active identities are native `0..8`, an
unlocked extra identity present in the payload, or `0xFFFF` for an empty slot.
Nonempty active identities cannot repeat. Sephiroth's independent identity is
`0x0100`; his presentation identity is `10`. Presentation identities select
assets and must never be used as native character-storage indices.

The 132-byte character record holds the extra character's game-format state;
the codec preserves its bytes without inventing stats or validating individual
equipment/materia fields. Semantic validation belongs to the gameplay adapter.

The earlier experimental `FF7PARTY` **version 1** sidecar used a digest of an
individual base save slot. Version 2 deliberately rejects it: a digest with
that meaning cannot be interpreted as a full-card digest. There is no automatic
migration, and the exporter does not accept standalone party payload files.

## Active Sephiroth and standard export policy

The base card must always contain a valid **native fallback party** for each
extended save. The extension records the actual expanded party. For example,
the extension may contain Cloud, Vincent, and independent Sephiroth as
`[0, 7, 256]`, while the base retains a separately validated native fallback
party chosen by the gameplay adapter.

The writer must retain the save's last verified native roster, or build and
validate a native roster through a game-aware adapter before saving. If it
cannot produce one, it must fail the extended save without replacing the last
good file. It must not truncate `0x0100` into a byte, write asset identity `10`
as though it were an independent playable character, or replace Vincent's
record. Original FFVII maps identity `10` to Vincent's storage row; silently
doing that would lose the distinction the mod is intended to preserve.

**The export tool does not choose a replacement character or repair party
fields.** It validates the container and emits the first 131,072 bytes exactly.
The native party, directory data, save checksums, and other games' data remain
unchanged. Its JSON report lists active extra identities so callers can explain
what will be omitted. This report is informational; it does not require a
second confirmation after the user has requested an export.

Expanded characters, their independent stats/equipment/materia, and their
active-party selections are absent from the standard export. The tool does
not return their equipment or materia to the native inventory, duplicate items,
or modify native inventory counts. An eventual inventory-transfer export
would require a separate game-aware transformation and could not promise
byte-identical base output. Keep the extended source file to retain that state.

## Export and inspection tool

From the game repository:

```powershell
python tools/ff7_save.py inspect "saves/extended.mcd"
python tools/ff7_save.py export-standard "saves/extended.mcd" --output "saves/standard-copy.mcd"
```

The same export command accepts an already standard raw card and creates an
exact copy. The output path is mandatory. The input is opened read-only, and
the tool never overwrites an existing output, including an alias of the input.
Validation finishes before output creation.

To avoid a partially visible result, the exporter writes and flushes a
temporary file in the destination directory, then publishes it using an
exclusive hard link. The destination appears only after the whole file is
written. A racing writer cannot be overwritten. Filesystems without suitable
hard-link support fail without a non-atomic fallback. Normal failures remove
the temporary file; abrupt process termination can leave a `.ff7-export-*.tmp`
file. Atomic visibility is not a guarantee against every filesystem or power
failure. Existing source and destination files are not changed during cleanup.

Inputs are read with a fixed maximum size plus one overflow byte. Unexpected
file sizes, versions, flags, duplicate entries, invalid IDs, malformed counts,
trailing data, CRC failures, and SHA mismatches cause a nonzero exit status and
no export. The tool does not download, bundle, or distribute save data.

## Truncation and recovery

A partial extension is an error, not a reason to fall back silently to the
base. An unsupported newer version is likewise preserved for a newer tool.
Neither codec nor exporter guesses missing fields or repairs checksums.

There is one unavoidable ambiguity: a file truncated to **exactly 131,072
bytes** is indistinguishable from an intentional standard export. It loads as
a standard card and has no extra metadata. No byte outside the base remains
to prove otherwise; this is why the runtime must commit the combined file
atomically and retain its previous good version during replacement.

If a nonempty extension is invalid, keep the original file and restore a
known-good backup of the **whole file**. Do not combine a base and extension
from different generations or recompute hashes merely to suppress an error.
For the specific case of a **stale full-card binding**, an explicit recovery
export is available:

```powershell
python tools/ff7_save.py export-standard "saves/stale.mcd" --output "saves/recovered-standard.mcd" --recover-base
```

This option permits only a mismatch between the current base SHA-256 and an
otherwise valid extension. Both CRC levels, supported versions, entry bounds,
directory references, and matching envelope/payload stored hashes must still
validate. It outputs the current complete base exactly, leaves the source
unchanged, and reports `recovered_stale_binding: true`. The stale metadata is
discarded from the exported copy, not repaired or rebound. The C runtime codec
remains strict and has no recovery bypass.

Truncated bases, malformed or truncated tails, unknown versions, and checksum
failures are never bypassed. Recovery cannot restore lost expanded-party state.
A valid base header alone does not prove that each game save is sound.

## Runtime integration contract

`src/ff7_party.h` exposes the in-memory roster, slot, and card types. The card
APIs perform hashing internally and use no file I/O or guest-memory writes:

```c
FF7PartyResult ff7_party_card_encode(
    const FF7PartyCard *card,
    const uint8_t *base, size_t base_size,
    uint8_t *out_tail, size_t capacity, size_t *written);

FF7PartyResult ff7_party_card_decode(
    FF7PartyCard *card,
    const uint8_t *base, size_t base_size,
    const uint8_t *tail, size_t tail_size);
```

`base_size` must be 131,072. Encoding returns only the tail; the frontend writes
`base + tail` as one transaction. `FF7_PARTY_CARD_EXTENSION_MAX` is 33,784 bytes.
A null/undersized output returns `FF7_PARTY_BUFFER_SMALL` and reports the needed
length without writing output. Card slots must be strictly ascending. Inputs,
outputs, and state must not overlap. Decoding validates into temporary storage
and replaces the destination only on success. It uses approximately 33 KiB
of stack scratch. A null tail with size zero successfully produces an empty
metadata map for a standard card; a nonempty invalid tail must not be ignored.

The frontend/game adapter must:

1. Read and validate the complete on-disk file before applying extra metadata.
   The guest memory-card device still exposes only the standard 128 KiB. A
   rejected refresh must report a save failure, rather than acknowledge a
   write that was not committed.
2. Associate a gameplay save/load with its verified FFVII directory slot.
   Restore that slot's metadata only after the matching native save has loaded.
3. Save the actual expanded roster in the slot payload while writing its
   validated native fallback representation and correct native checksums into
   the base. Native Vincent's record remains independent.
4. Rebind all retained slot payloads whenever **any** base byte changes. Remove
   stale entries when files are deleted, replaced, or moved; never merely
   rehash stale metadata onto an unrelated new save.
5. Write and flush a temporary combined file, then atomically replace the
   intended runtime save path according to the frontend's backup policy. Do
   not append in place or let a generic 128 KiB flush discard the tail.
6. Snapshot and restore guest card bytes and expanded metadata together for
   rewind/savestates. Card switches, save-as, disc changes, and failed writes
   must not mix generations or leak one card's metadata to another.
7. Expose standard export through a deliberate command/UI action. Preserve the
   extended source and explain that its extra characters are omitted from the
   exported copy. Use the same validation and exact-base policy as the tool.

The low-level `ff7_party_encode/decode` functions remain available for a single
version 2 payload. Their caller-supplied digest must now be the SHA-256 of the
whole base card. They are not sufficient for a save-file transaction on their
own; prefer the card APIs.

## Developer runtime adapter

`src/ff7_party_save.c` registers plugin `ff7.party-save`, selected by the
default-off, developer-channel `party-save` feature in `ff7.expanded-party`.
Activation installs callbacks using `memcard_set_extension_codec`. The shared
frontend must clear that codec registration before each new mod session and
invoke the loader on card initialization/reload. The adapter has no path I/O.

The adapter maintains independent host state for memory-card ports 0 and 1.
Activation clears both states. Each load clears the target state first,
then performs the complete card-extension validation. A failed load leaves
that card's refresh disabled, rather than retaining data from the previous
file. The runtime's opaque-tail preservation policy must retain the original
file/tail when refresh is rejected; native card access remains a separate
transport concern.

Raw cards receive no new tail, unlocked characters, or invented metadata. A
valid loaded extension is re-encoded against the current native base on flush.
This updates the full-card hashes and CRCs without changing native bytes.
The adapter rejects refresh when a referenced directory frame is no longer
an allocated first frame, fails its XOR, or changes its first 32 descriptor
bytes (allocation, size, chain, filename and reserved byte). This catches
obvious deletion/replacement/reallocation instead of rebinding old character
state to the new file.

This descriptor guard does not detect every same-filename save replacement,
nor does it establish that loaded extra stats match the player's latest game
progress. There are no gameplay hooks to populate/update individual slot party
states yet. Rewind/savestates do not synchronize this host state yet. Consequently
this feature is persistence plumbing for developer testing, not a complete or
playable expanded-party save lifecycle.

Load returns zero only after validation; rejected loads return negative. Save
returns zero for an ordinary raw card, the encoded byte count for a valid
loaded tail, or negative to abort refresh/flush. Insufficient output capacity
also rejects the write. There is no implicit stale-hash recovery. The standalone
exporter's explicit `--recover-base` option is not used by runtime callbacks.

Observability counters use the `ff7.party_save.` prefix: `activate`, `load`,
`load_ok`, `raw_load`, `save`, `save_ok`, `raw_save`, `reject`, `load_reject`,
`save_reject`, and `directory_changed`. They expose callback attempts and
outcomes without logging raw character records or file contents.

## Validation performed

Standalone C tests cover roster separation, payload and card corruption,
every nonempty extension truncation, transactional decode, full-card binding,
maximum capacities, directory-slot validation, and rejection of version 1
payloads. Python tests cover the same format boundaries and actual file export,
including existing outputs, input aliases, publication races, flush/publication
failures, and the explicit-output CLI. Optional C/Python interoperability tests
cross-decode and compare complete encoded tails byte for byte, including
SHA-256 and both CRC levels. Tests use synthetic cards, not distributed saves.

Focused adapter tests use stub transport/observability functions and cover
two-card isolation, strict reloads, no automatic raw-card extension, current-base
rebinding, deletion/descriptor/XOR rejection, output capacity, stale binding,
and activation reset. `ff7_party_save_integration` also links the real codec,
adapter and framework card transport. It verifies file refresh, preserved extra
records, stale-binding rejection and explicit standard-card import. It does
not establish native FFVII save fallback or actual gameplay state creation.

No test here establishes that Sephiroth's game-specific save/load lifecycle,
native fallback projection, or selectable playable-party behavior is complete.
