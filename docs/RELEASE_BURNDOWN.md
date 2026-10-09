# FFVII first release burndown

Updated 2026-10-09. This is the current scope and remaining-work record for the
FFVII enhancement mods. Gameplay implementation is **paused**. The owner has
authorized updating documentation and Beads only; implementation, builds and
live testing require explicit authorization to resume.

**Work order:** finish the loading and visuals review/integration first, then
return to Sephiroth. The owner moved the Sephiroth work to the end.

## First release scope

Sephiroth is an independent selectable party member alongside Cloud and Vincent,
with his own equipment, materia, battle control, progress and persistent record.
The initial release needs **Masamune and Crescent Arc only**, both at level 1.
The original story-selected field and world-map avatars remain in control.
Added-character field leadership is a future enhancement.

Expanded-party metadata stays in the same memory-card file, after its standard
128 KiB base. Standalone save tools are sufficient. Export uses
`tools/ff7_save.py export-standard`; standard raw-card import/load uses the
existing card path. A separate import CLI is not currently implemented, and
recomp-ui export/import controls are not a requirement.

Loading acceleration and the enhanced 1080p/adaptive renderer remain separate
parts of the original project. The custom renderer supersedes Cobalt's previous
widescreen mod. Prerendered fields currently retain 4:3 composition, and FMVs use
native presentation. Full field-background widening remains unresolved renderer
scope; the current implementation must not be described as completing it.

## Completed foundation and checks

- The three owned USA discs are copied locally and excluded from version control.
  Framework/UI updates, native Windows Release generation/build and opening
  movie, field and battle checks have passed.
- Independent registry/records and guarded PHS, Equip, Materia, Status, Item,
  Magic, battle, rewards and native save/load adapters are implemented.
  Original-MIPS tests on all three discs cover native Cloud/Vincent and extras.
- Live diagnostics pass Attack, Potion, Cure/MP spending, Defend, low-HP posture,
  mortal death/Phoenix Down revival, victory, own portrait and independent EXP/AP.
  Three-member PHS and reserve swaps have also passed.
- Masamune and Crescent Arc both execute in live battles, clear the gauge,
  update independent counters and reach native victory. Native battle return
  and an ordinary field transition have passed.
- Actual BIOS saves, fresh extended-card title-to-field loads and an exact
  standard export have passed. The exported standard card also loads through
  the existing native card path. Synthetic tests cover corruption, card/slot
  binding, replacements, two cards, pending writes and rewind.
- Guarded host LZS decompression passes original-code comparisons, including
  overlapping input/output. Enhanced rendering has passed opening-field and
  first-battle checks. Native CD cadence is retained because accelerated sector
  bursts broke actors; other decompression/loading paths still run natively.

The last built gameplay checkpoint is `a8e6473`: 736 instruction addresses and
11 entry hooks, with 18 CTests and 19 Python save/export tests passing. Game PR
[#4](https://github.com/TechnicallyComputers/Final-Fantasy-VII/pull/4) remains a
draft. Diagnostic early-scene permission changes are test setup, not release
behavior. The working tree also contains an uncommitted field-control prototype;
its extra hook and opt-in must be excluded from first-release integration.

## PR readiness

Loading and rendering are reviewable implementations in draft game PR #4, which
currently also contains expanded-party work. They are not yet isolated changes
ready to merge independently.

| Component | Current state | Remaining before its release integration |
| --- | --- | --- |
| Guarded LZS acceleration | Original-code and live startup checks pass; ready for focused code review. | Isolate the change/dependencies and address the separately tracked remaining loading bottlenecks. |
| Enhanced renderer | Opening field/battle work and the implementation is reviewable. | Representative world-map/wide-aspect culling/presentation checks and independent integration; authored fields currently stay 4:3. |
| Sephiroth | Experimental implementation with passing core battle/menu/save evidence. | Deferred until loading/visuals work is handled; complete the reduced character acceptance below. |

## Remaining first release work

Each unchecked item is pending, even where some underlying checks already pass.

### Loading and visuals first

- [ ] **R7 Remaining loading bottlenecks** (`beads-dmfi`). Profile the remaining
  heavy loads and add safe acceleration for useful bottlenecks. Preserve CD,
  XA/SPU and FMV behavior. Validate each newly accelerated path; current LZS
  acceleration does not establish elimination of all loading.
- [ ] **R6 Renderer acceptance** (`beads-dmfi`). Review representative battle,
  field, world-map and FMV scenes at normal and wide aspects; check 1080p scaling,
  PGXP, filtering and geometry/culling outside the original frame. Document the
  field-background limitation and resolve its remaining scope before closing
  renderer work.
- [ ] **R8 Release integration and PRs** (`beads-p389`, `beads-dmfi`,
  `beads-uyog`). Prepare independently reviewable loading/renderer changes first,
  reconcile their framework dependencies and build/check the intended
  configuration. Keep deferred character prototypes separate. Repeat integration
  for Sephiroth after its later acceptance, and update the final evidence/PRs.

### Sephiroth integration last

- [ ] **R1 Limit availability and progression** (`beads-uyog`). Expose only
  Masamune/Crescent Arc; prevent higher-level prototype content appearing in the
  release preset. Verify Crescent Arc learning/unlock and save/reload of the
  two-move progression and gauge. Define compatible handling of existing
  diagnostic records that selected a higher prototype level. Preserve the
  extension mechanism and saved record layout.
- [ ] **R2 Animation and command review** (`beads-uyog`). Briefly exercise each
  supported command category and review damage, cover, item, casting and the
  procedural poses. Correct visible floor-contact, weapon-grip or clipping
  defects. Seven bespoke limit animations/effects are outside this release.
- [ ] **R3 Independent party and menu acceptance** (`beads-uyog`). Exercise one
  live party containing recruited Cloud, Vincent and Sephiroth, a reserve swap,
  representative equip/unequip and materia exchange, an incompatible-item
  rejection, and menu item/magic use. Verify native records remain independent.
- [ ] **R4 Existing story compatibility** (`beads-uyog`). Check representative
  forced-party changes, temporary removal, Wutai materia theft/return and
  field/battle/world-map transitions. Preserve the original story avatar.
  New dialogue, scene rewrites and a complete story traversal are not release
  gates; expand coverage when a representative check exposes a defect.
- [ ] **R5 Save lifecycle and disc changes** (`beads-uyog`, `beads-p389`). Check
  interrupted saving and rewind during a save, including safe rejection/recovery
  and the documented partial-sector behavior. Verify Sephiroth persistence
  through disc changes and record the standard-card import/load procedure.
  Standard export/import requires no new launcher UI.

## Focused validation plan

Passing checks should be reused until relevant code, assets or configuration
change. The reduced matrix focuses on distinct behavior and high-impact failures.

| Area | Remaining representative coverage |
| --- | --- |
| Three discs | Execute shared behavior once where executable/overlay bytes match; verify guards on all three. Retain actual disc changes and checks for disc-specific assets. |
| Two release limits | Reuse the passing single/all-target battles. Check release availability, Crescent Arc learning and saved progression; rerun battle playback when those paths change. |
| Party combinations | One recruited Cloud/Vincent/Sephiroth party, one reserve swap and a native regression check. Reuse existing synthetic capacity and independent-record tests. |
| Equipment and materia | Representative successful transactions and one incompatible-item rejection, with inventory/AP conservation. No every-item-by-every-character matrix. |
| Fields | Representative live transition and crowded-field smoke checks. Reuse existing original-code checks for saturated fields and delayed initialization. |
| Rendering | A scene set covering battle, field, world map and FMV at normal and wide aspects; expand on observed failures. |
| Animations | A short playback for every command category, concentrating visual review on invented or remapped motions. |

Keep stronger coverage for save round trips/export/import, interruption/rewind,
disc changes, forced-party and Wutai transactions, and every new loading HLE.
Reuse the already passing corruption and lifecycle suites; update them when the
corresponding behavior changes. Whole-game certification and exhaustive roster,
item and scene combinations are not prerequisites for this initial release.

## Deferred enhancements

- Field-leader control, camera/follower acceptance and arbitrary world-map leaders.
  The [field-leader patch note](FIELD_LEADER_ENHANCEMENT.md) preserves the findings
  and resumption criteria.
- Five additional prototype limits, levels 2-4, final mastery and any additional
  choreography/effects. Extension points are recorded in the
  [save-format architecture](SEPHIROTH_SAVE_FORMAT.md#additional-character-architecture).
- Fine balance tuning beyond obvious functional problems.
- PHS paging and additional portrait banks for larger future character rosters.
  Sixteen-record storage capacity is already tested synthetically.
- recomp-ui save export/import integration. Standalone tools satisfy the request.

## Tracking and integration

The central Beads database is `F:\Software\beads\issues`; no per-game database
is used. `beads-z9df` owns the game epic; `beads-p389`, `beads-dmfi` and
`beads-uyog` own the work above. Historical milestone comments remain evidence
of what was observed; this scope and current acceptance criteria supersede
older requirements for a field leader or seven release limits.

Bootstrap PR [#3](https://github.com/TechnicallyComputers/Final-Fantasy-VII/pull/3)
and game PR [#4](https://github.com/TechnicallyComputers/Final-Fantasy-VII/pull/4)
are accompanied by framework PRs
[#604](https://github.com/RetroPortingToolKit/psxrecomp/pull/604),
[#606](https://github.com/RetroPortingToolKit/psxrecomp/pull/606) and
[#613](https://github.com/RetroPortingToolKit/psxrecomp/pull/613).
The tested framework pin is `56c5b9e9`; recomp-ui is pinned at `7e884a22`.
