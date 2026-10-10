# Sephiroth and expanded-party save format

The specified persistence format stores expanded-party metadata **in the memory-card file**,
after the standard 128 KiB card image. It does not require a separate sidecar.
The first 131,072 bytes retain the standard card representation. Exporting a
standard card copies those bytes exactly and removes the extension.

This document specifies `FF7MCEXT` version 1 and its nested `FF7PARTY` version 3
payloads. Version 2 full-card payloads remain readable. The experimental
Sephiroth mod (`ff7.sephiroth`, plugin `ff7.party-gameplay`) now integrates the guest roster with guarded original
SAVEMENU save/load instructions, native fallback projection and the shared card
extension transport. Pending writes live in snapshot-owned enhancement memory.
The earlier `party-save` adapter remains a codec test fixture; it is no longer
offered in the catalog because the gameplay adapter must own card persistence.
The exporter currently runs as a standalone command. A live BIOS save, exact
standard-card export and extended-card title-to-field reload have passed. Native
checksum and preview tests, synthetic card lifecycle tests and independent limit
progression checks also pass. Live single/all-target limits complete and return
through native victory into the field. First release is scoped to Masamune and
Crescent Arc, retaining the original story-selected field and world-map avatars.
Restricting the current seven-technique prototype to those two limits remains
implementation work. Learning/unlock, saved progression, interrupted-write/rewind
behavior and representative existing story transitions remain acceptance checks.
Higher levels, final mastery and added-character field leadership are deferred.
Standalone save export/import is sufficient; recomp-ui integration is not required.
See the [first-release burndown](RELEASE_BURNDOWN.md) for the current acceptance
plan and the [field-leader note](FIELD_LEADER_ENHANCEMENT.md) for the optional patch.

## Additional-character architecture

Sephiroth is the first entry in an added-character registry. `FF7PartyProfile`
separates a persistent 16-bit identity from its asset paths, template, equipment
compatibility, growth rules, motion policy and limit policy. Multiple entries can share a
stock presentation or rule set while retaining independent character records.
Future characters add descriptors and the corresponding asset/ability adapters;
they do not replace Vincent or consume another native character's record.

The version 3 payload stores a variable-length roster of up to sixteen
added records per save, plus active and stored field-party identities. These limits are
explicit format bounds, not an assumption that only Sephiroth exists. Increasing
them requires a versioned migration. A reader that lacks a character's registered
profile refuses to publish that roster; it must preserve the metadata and use
the native fallback instead of interpreting an unknown identity as a stock ID.

`src/ff7_party_game.c` gives live additions separate Expansion 1 records. Guest
byte IDs 11 through 26 are temporary handles for those records; persistent IDs
start at 0x100. On load, proxies are rebuilt from canonical identities. The
original IDs 9 and 10 retain the flashback aliases. Native alias tables remain
unchanged: guarded instruction adapters redirect only added-character operands.

The live registry, records, alias scratch and native fallback are guest memory,
which psxrecomp captures with its main RAM and devices. Host globals hold only
immutable descriptors and activation-fixed addresses. The bridge's lifecycle
tests exercise two additions with one presentation, record reordering on load,
atomic PHS swaps, rejected unknown profiles and whole-state rewind. This closes
the live-roster ownership gap. The gameplay adapter below supplies slot-level
packet matching and native projection; complete live gameplay acceptance is
still separate from these storage tests.

PHS currently retains its nine reserve cells and one additional portrait atlas
cell. Materia exchange has a separate expanded 25-entry list. Reserve overflow
is counted; future larger rosters need paging and portrait banks. These UI bounds
are separate from save/storage capacity and must be addressed before enabling
additional characters beyond what those screens can show.

Limits are profile-selected too. Policy zero retains the native rules; the current
Sephiroth prototype uses policy one with seven techniques across four levels.
First release will expose only the two level-1 techniques, Masamune and Crescent
Arc. The other five are future content, and fine balance tuning is deferred.
The prototype's reserved attack IDs 96 through 102 use existing strike/sweep
action scripts on his own body and weapon rig. A future character needs an
explicitly registered policy,
verified unused attack entries and suitable action/asset adapters. Adding a
descriptor alone does not make an arbitrary model or ability compatible.

Future limits use `FF7LimitMove` and `FF7LimitPolicy` in
`src/ff7_party_limit.h`, policy data in `src/ff7_party_limit_policy.c`, and the
profile's `limit_policy`. Adding a technique requires a unique learned bit and
verified unused attack ID, encoded name/description, targeting and power, plus
compatible body/weapon choreography. The guarded menu, learning, battle dispatch
and attack-cache adapters in `src/ff7_party_limit.c` must cover that policy.
The current seven-move arrays, IDs 96-102 and fixed guest storage are implementation
bounds; extending them requires updating those bounds and validating the new path.
Progression remains in the independent record fields below. A new technique does
not itself require a new save envelope version; changing the saved layout does.

## Saved limit progression

Limit progression uses the existing fields inside each extra member's independent
132-byte record. It does not change the `FF7PARTY` version 3 layout or introduce
host-only progress. Offsets below are relative to those 132 character bytes,
not to the containing 136-byte envelope entry.

| Offset | Bytes | Meaning |
| --- | ---: | --- |
| `0x0E` | 1 | Selected limit level; prototype supports 1 through 4, first release targets level 1 |
| `0x0F` | 1 | Limit gauge |
| `0x22` | 2 | Learned-technique bit mask |
| `0x24` | 2 | Enemy kills |
| `0x26` | 2 | Level 1 limit uses |
| `0x28` | 2 | Level 2 limit uses |
| `0x2A` | 2 | Level 3 limit uses |

New Sephiroth records start at level 1 with an empty gauge, learned mask 1 and
zero counters. Masamune and Crescent Arc use bits 0 and 1; the current prototype
learns Crescent Arc after eight level-1 limit uses. The remaining thresholds
describe future content, not first-release acceptance. The prototype's move bits
are 0, 1, 3, 4, 6, 7 and 9. The second moves at
levels 1, 2 and 3 require 8, 7 and 6 uses respectively; the first moves at
levels 2 and 3 require 80 and 160 kills. The final move requires the previous
six techniques and 320 kills. These are provisional mod balance values.

When loading an older expanded-party record for a registered limit policy, the
bridge adds only its first-technique bit. It preserves the selected level,
gauge, other learned bits, kill count and use counters. Native characters and
profiles without a registered policy keep their original bytes. The next
ordinary game save stores this progression with the rest of the independent
record; standard export omits the entire added-character record.

Field assets are also profile-selected. The loader appends independent script
entities and model descriptors, preserving original entity numbers and NPC data.
The loader uses a separate 32-model state arena and guarded original-code
adapters for field state access and delayed actor creation. Native entity numbers,
NPC records and the original CHAR counter remain unchanged. All three discs pass
isolated checks for the 11 fields that already use 16 models, plus ordinary and
delayed-initialization maps. Verified field IDs select complete BSX filenames
instead of relying on truncated names in DAT headers. Model, script and workspace
capacity checks reject unsupported combinations before publication. These runtime
bounds are separate from the saved roster's 16-extra capacity. Representative
transitions and existing story transactions remain first-release checks.
Controlling an added character as the field leader is an optional future feature;
its profile-selected prototype does not change the save envelope layout.

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
characters. The maximum tail is 34,024 bytes (`0x84E8`), so the maximum complete
file is 165,096 bytes (`0x284E8`).

An empty extension is 64 bytes. One save entry containing one extra character
uses a 288-byte tail, for a total file size of 131,360 bytes (`0x20120`).

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
| `0x04` | 4 | Payload byte count, `80..2256` for v3; v2 starts at 64 |
| `0x08` | variable | One complete `FF7PARTY` version 2 or 3 payload |

A directory index is only meaningful together with the bound card image.
Deleting or replacing a save must remove its old metadata before rebinding.
Moving a save requires explicitly moving its metadata to the new directory
index. A matching index in a different file is not sufficient evidence that
the metadata belongs to the same save.

## Party payload: `FF7PARTY` version 3

| Payload-relative offset | Bytes | Field |
| --- | ---: | --- |
| `0x00` | 8 | ASCII `FF7PARTY` |
| `0x08` | 2 | Payload version: `3` |
| `0x0A` | 2 | Header size: `80` |
| `0x0C` | 4 | Payload size: `80 + 136 * member_count` |
| `0x10` | 2 | Extra-member count, `0..16` |
| `0x12` | 6 | Three active identities, each a 16-bit integer |
| `0x18` | 32 | SHA-256 of the same entire 131,072-byte base card |
| `0x38` | 4 | Reserved: zero |
| `0x3C` | 4 | CRC32 of this payload, with these four bytes zeroed |
| `0x40` | 6 | Three stored field-party identities, each a 16-bit integer |
| `0x46` | 3 | Stored native alias hints: 255, or 9/10 for canonical 6/7 |
| `0x49` | 1 | Stored field-party bank present: 0 or 1 |
| `0x4A` | 6 | Reserved: zero |
| `0x50` | variable | Extra-member records |

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

The stored roster follows the same identity/unlock/duplicate rules. The verified
NTSC-U FIELD functions at `0x800CF60C` and `0x800CF5A0` copy the three-byte party
bank at Savemap offset `0xCAD` (`0x8009D391`) to/from the active party. Version 3
stores that bank canonically so proxy reordering on load preserves the intended
members. Native flashback IDs 9/10 have explicit hints to retain their original
presentation after canonicalization. An absent bank contains three `0xFFFF`
identities and three 255 hints. Version 2 used a 64-byte header and had no bank;
loading it retains the already-loaded native base bank, rather than inventing one.

The 132-byte character record holds the extra character's game-format state;
the codec preserves its bytes without inventing stats or validating individual
equipment/materia fields. Semantic validation belongs to the gameplay adapter.

The earlier experimental `FF7PARTY` **version 1** sidecar used a digest of an
individual base save slot. Versions 2 and 3 deliberately reject it: a digest with
that meaning cannot be interpreted as a full-card digest. There is no automatic
migration, and the exporter does not accept standalone party payload files.

## Active Sephiroth and standard export policy

The base card must always contain a valid **native fallback party** for each
extended save. The extension records the actual expanded party. For example,
the extension may contain Cloud, Vincent, and independent Sephiroth as
`[0, 7, 256]`, while the base retains a separately validated native fallback
party chosen by the gameplay adapter.

The gameplay writer retains the last wholly native party. For its private
outgoing copy, it keeps currently selected native members and replaces each
extra proxy with an unused member from that fallback, or 255 for an empty slot.
It projects the stored field-party bank too. Preview IDs, leader name/level and
HP/MP are rebuilt from the projected native leader, and the original 4340-byte
Savemap checksum is recomputed (CRC16 polynomial `0x1021`, initial `0xFFFF`,
complemented result over bytes 4..4339). Native character records and inventory
bytes remain unchanged. Live records and selections are never temporarily
replaced during saving. If preparation fails, the adapter sends the original
BIOS open path an empty filename so its normal error path returns without a
card write. It must not truncate `0x0100` into a byte, write asset identity `10`
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
`base + tail` as one transaction. `FF7_PARTY_CARD_EXTENSION_MAX` is 34,024 bytes.
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
version 3 payload, with version 2 decoding supported. Their caller-supplied digest must be the SHA-256 of the
whole base card. They are not sufficient for a save-file transaction on their
own; prefer the card APIs.

## Gameplay save adapter

`src/ff7_party_game_save.c` shares plugin `ff7.party-gameplay` with the independent
roster and menu/battle adapters. It verifies thirteen original instruction words
around each seam. At `0x801D2900`, after SAVEMENU finishes constructing its 8192-byte
file at `0x801E6F38`, it snapshots added records, projects the private outgoing
Savemap and captures the exact packet plus filename in Expansion 1. The filename
must use `bu00:` or `bu10:` and identify one allocated, checksum-valid, single-block
directory entry of exactly 8192 bytes. It does not guess from a UI row number.

The BIOS writes and flushes individual 128-byte sectors. Returning a flush
failure for every partial packet would make the game retry those sectors rather
than finish the save. The adapter accepts ordinary sector writes, removes the
target's previous metadata while the replacement is incomplete, and attaches the
new roster only when all 8192 current card bytes match the captured packet.
Every retained entry is rehashed against the resulting complete base card.
Deleted, reallocated or renamed entries lose their metadata. Each framework
flush publishes its base and tail together; this does not make the entire
multi-sector native BIOS operation atomic. An interrupted native write can leave
an incomplete native save, as in the original game, and never gains new metadata
through a partial-packet match. Pending state remains retryable across host
publication failures and rewinds with guest RAM. The original save function's
return seam clears its pending transaction.

After a successful original load and its caller's checksum comparison at
`0x801D49B0`, the adapter checks the exact
filename, allocated slot, full file equality and native checksum before restoring
that slot's added records and both parties. An ordinary save resets added records
from immutable kernel templates rather than keeping another game's progress.
Missing character profiles retain the native fallback and leave on-card metadata
intact until an explicit new save replaces it. Invalid card extensions reject
flushing; there is no automatic hash recovery. The new-game-only seam at
`0x80011DBC` resets added progress after the original kernel and native party reset;
the shared native reset routine also runs before the title and is unsuitable alone.

The restoration seam is deliberately after the caller compares the original
Savemap CRC. Restoring extra party handles inside the earlier file-read return
would change checksum-covered bytes before that comparison and reject a valid
save. The successful caller branch retains the loaded filename at caller stack
pointer minus `0x30`; the intervening checksum routine does not overwrite it.
The adapter changes no registers, return values or stored native checksum.

The framework restores card base/tail bytes and invokes the codec loader to
rebuild host card caches. The live roster, field bank and pending packet are guest
snapshot bytes, so no host roster from a later frame is republished on rewind.
Save-menu BIOS I/O and a fresh title-to-field reload have passed live checks.
Live rewind during saving still needs acceptance testing.

## Developer runtime adapter

`src/ff7_party_save.c` retains the earlier `ff7.party-save` codec test fixture.
It is not selectable in the mod catalog. Its isolated tests install callbacks
using `memcard_set_extension_codec`; gameplay uses the slot-aware adapter above.
The shared
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

The gameplay adapter tests additionally cover all 64 sector writes of a synthetic
packet, exact filename/full-packet matching, deletion/replacement, two-card
isolation, native fallback and field-bank projection, reload, pending-packet
rewind, failed preparation and native PC preservation. An original-MIPS oracle
matches eight checksum inputs and the full preview routine for native Cloud,
Vincent and an independent proxy on all three discs. C/Python v3 bytes match and
both readers migrate v2 without inventing its missing bank. These tests do not
establish complete playable-party behavior. Separate live checks validate an
original BIOS save with Sephiroth's own EXP, equipment and materia, a standard
export identical to the 131,072-byte native base, and a fresh title-to-field load
of the extended card. The load restores both party banks only after the original
checksum succeeds; the stored CRC remains unchanged. Live rewind during saving,
disc switching and whole-game story coverage remain unvalidated.
