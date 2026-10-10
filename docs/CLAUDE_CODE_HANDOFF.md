# Claude Code handoff for FFVII validation and the Sephiroth MVP

Prepared 2026-10-09. The owner's requested continuation is to validate the
existing loading/rendering work, fix observed failures, then finish an MVP
independent Sephiroth party member. Codex prepared this handoff without resuming
gameplay implementation or testing. Earlier pause markers describe that stopped
Codex session; the owner's continuation prompt to Claude authorizes the work below.

## Scope and owner constraints

- Work solo. Do not resume the old Sephiroth subagent or delegate unless the
  owner explicitly authorizes agents for this continuation.
- Loading/visuals validation comes first; Sephiroth comes last. Use the focused
  matrix below. Do not turn this into exhaustive whole-game certification or
  finish every possible loading/renderer enhancement before attempting the MVP.
- Sephiroth must be a real independent party member alongside Cloud and Vincent:
  selectable in PHS, player-controlled in battle, with independent stats,
  equipment, materia, rewards/growth and persistent progress. Do not replace
  Vincent or repurpose a native record as the live extra character.
- **Only Masamune and Crescent Arc are required for release.** Both belong to
  level 1. Five other prototype limits, levels 2-4, final mastery, bespoke extra
  effects and fine balance tuning are deferred. Preserve the ability to add
  techniques later; do not spend this MVP inventing five more.
- **Sephiroth need not be the exploration leader or have a world-map actor.**
  Keep the normal story-selected field/world-map avatar. Battle ordering must
  not silently break exploration control. No new dialogue, scene rewrites,
  follower/camera feature or general party-leader unlock is required.
- His battle animations must look usable: review standard commands and the
  invented/remapped motions, then fix obvious defects. Existing compatible
  motions are acceptable; unique cinematics for every action are not a gate.
- Keep the extensible character registry and independent records for future
  additions. Larger-roster PHS paging/portrait banks are future work.
- Saves may extend the same memory-card file. Standalone save tools are fine;
  no recomp-ui export/import controls are required. Export must produce the
  exact standard base in a new file, preserving the source.
- Everything is implemented as mods. PRs target Cobalt's
  `TechnicallyComputers/Final-Fantasy-VII`. The custom Tomba-derived renderer
  supersedes the original widescreen mod. Owned discs/assets/BIOS/saves/captures
  and Ghidra databases must never be committed.

## Exact checkout and integration state

Game repo: `F:\Projects\psxrecomp\Final-Fantasy-VII`, nested inside the outer
framework workspace. Branch: `codex/ff7-enhancement-mods`.

- Last built gameplay checkpoint: `a8e64733b90d8dbaf93a7a4e9a2ea32ed4dee7a5`.
  This had 736 instruction addresses, 11 entry hooks, 18 passing CTests and
  19 passing Python save/export tests including actual C/Python parity.
- Documentation/scope checkpoint: `1d5d414b6ec8da3e4d7ae36cc3756717ddd574a7`,
  pushed to the fork. This is the verified HEAD before adding this handoff;
  it changed documentation and acceptance reports, not gameplay.
- Framework submodule: `56c5b9e91954924cfe4664771ad06b59d28b1526`.
  recomp-ui: `7e884a227accea91ddb378671bd49aaeeea13371`.
- `origin` is Cobalt's upstream. Push to `fork`,
  `https://github.com/mstan/Final-Fantasy-VII.git`; an upstream push previously
  failed with 403.
- Bootstrap PR: [#3](https://github.com/TechnicallyComputers/Final-Fantasy-VII/pull/3).
  Combined enhancement/party draft: [#4](https://github.com/TechnicallyComputers/Final-Fantasy-VII/pull/4).
  Loading and renderer implementations are reviewable there but not yet isolated
  for independent merging.
- Framework PRs:
  [#604 session resolution](https://github.com/RetroPortingToolKit/psxrecomp/pull/604),
  [#606 card extensions](https://github.com/RetroPortingToolKit/psxrecomp/pull/606),
  [#613 shared overlay callbacks](https://github.com/RetroPortingToolKit/psxrecomp/pull/613).
  Check their current state before integrating; they were stacked dependencies,
  not already merged, at the previous checkpoint.

Read [RELEASE_BURNDOWN.md](RELEASE_BURNDOWN.md),
[SEPHIROTH_SAVE_FORMAT.md](SEPHIROTH_SAVE_FORMAT.md), and
[FIELD_LEADER_ENHANCEMENT.md](FIELD_LEADER_ENHANCEMENT.md) first. The latest owner
constraints above supersede historical seven-limit/field-leader acceptance notes.

### Preserve the uncommitted field control prototype

The working tree has 16 modified files from optional field-control work. The
new BF callback, its configured 737th hook and Sephiroth's profile opt-in have
not passed a full production build/live acceptance. They are outside the MVP.
The fields below were still modified when this handoff was prepared:

```text
game.toml
mods/preloaded/packages/ff7.expanded-party/field-hooks.evidence.json
mods/preloaded/packages/ff7.expanded-party/field-hooks.validation.json
src/ff7_party_field.c
src/ff7_party_field_sites.inc
src/ff7_party_game.c
src/ff7_party_game.h
tests/test_ff7_party_battle.c
tests/test_ff7_party_field.c
tests/test_ff7_party_field_loader.c
tests/test_ff7_party_game.c
tests/test_ff7_party_menu.c
tests/test_ff7_party_rewards.c
tools/inspect_ff7_field_hooks.py
tools/test_party_field_against_retail.py
tools/test_party_field_loader_against_retail.py
```

Preserve this work before changing or separating it; do not reset/clean it away.
An isolated worktree from the committed baseline is an option. Owned discs,
local saves, analysis fixtures and build artifacts are ignored and will not
appear in a new worktree; configure their paths deliberately. Do not blindly
rebuild the 737-hook prototype and call it the intended release configuration.
The field-leader note records the root cause, guard, 174 original-code calls
and diagnostic movement proof for a future enhancement.

## What already works

### Loading and visuals

The default-off renderer uses psxrecomp's Tomba hardware path, integer internal
resolution scaling, adaptive/fixed aspects, PGXP propagation and filtering.
Opening field and first-battle checks pass. A 1080p request currently selects
5x raster scale at 240 lines. Prerendered fields retain 4:3 and FMVs retain
native presentation; world-map/wide culling coverage remains acceptance work.

Guarded host LZS passes original-MIPS comparisons on 600 generated streams,
retail assets, startup streaming overlap and all 32 registers. Unsupported inputs
fall back. Preserve physical input/output alias handling: writes can overwrite
unread compressed input. Native CD cadence remains because sector-burst
acceleration produced incomplete actors. Gzip/other loaders are still native;
do not claim all loading is eliminated.

### Party, battle and persistence

Guarded adapters exist for PHS, Equip, Materia, Status, Item, Magic, Wutai's
ranked materia theft/return, battle models/control, EXP/AP/results and native
save/load. All-three-disc original-code tests exercise Cloud/Vincent/extras.
Live checks pass Attack, Potion, Cure/MP spending, Defend, low-HP posture,
mortal death/Phoenix Down revival, own result portrait and independent EXP/AP.
Three-member PHS/reserve swaps pass. Masamune and Crescent Arc complete live
single/all-target battles, consume gauge, update own counters and reach native
victory. Battle return and a normal field transition pass.

Actual BIOS SAVE, fresh title-to-field extended LOAD and exact standard export
pass; the exported standard card also loads. Diagnostic opening-scene permission
changes are test setup, not normal unlock rules. Live recruited Vincent alongside
Cloud/Sephiroth still needs a realistic check: unrecruited native row 7 initially
contains a Sephiroth template, so it is not proof of actual Vincent coexistence.

The registry separates persistent 16-bit identity (Sephiroth `0x100`) from guest
handles 11-26. Extras own 132-byte records. Native IDs 0-8 and flashback aliases
9/10 remain native. The format supports 16 extra records; UI capacity is smaller.
Shared guest-memory state, records and pending card writes rewind with snapshots.

## Validation first and MVP completion second

1. Establish the intended configuration, preserve/exclude the optional prototype,
   and verify build/codegen inputs agree. Use the passing baseline evidence;
   rerun checks when relevant source/configuration changes.
2. Validate loading/visuals with a small scene set: battle, field, world map and
   FMV, at normal and wide aspects. Check resolution/PGXP/filtering and culling
   beyond the original frame. Test mods-off versus the selected mod-on path.
   Fix observed failures, record limitations, and prepare independent reviewable
   integration where practical. New full-background widening or elimination of
   every load is not a prerequisite to the party MVP.
3. Restrict release availability to the two level-1 limits. Current code still
   defines seven; the scope change has not been implemented. Masamune is attack
   ID 96/learned bit 0, Crescent Arc ID 97/bit 1. Current Crescent Arc learning
   is eight level-1 uses. Prevent higher prototype levels/learning/mastery from
   surfacing in the release preset; handle old diagnostic higher-level records
   compatibly. Keep native characters and save layout unaffected, and preserve
   extension points in `ff7_party_limit_policy.c`, `.h` and the guarded adapter.
   Update seven-move assertions to match the accepted release profile; optional
   future-content tests must not force five additional release techniques.
4. Exercise one real recruited Cloud/Vincent/Sephiroth party, PHS/reserve swap,
   weapon/armor/accessory equip and unequip, incompatible-item rejection, materia
   placement/removal/exchange, and representative menu item/magic use. Check
   inventory/AP conservation, derived stats and native record independence.
5. Briefly play each supported battle command/animation category. Prioritize
   attack, both limits, casting, items, damage/cover, Defend, low HP, death,
   revival and victory; include differing summon/E.Skill choreography when
   relevant. Correct obvious grip, floor contact, clipping and missing motions.
   Sephiroth has 17 original body motions versus Cloud's 40. Current item/cover
   fallbacks reuse his own casting/evade poses; near-death/death/Defend are
   provisional paired body/weapon motions. Functional playback does not establish
   polished appearance. Compatible fallback motions are acceptable for the MVP.
6. Check representative forced-party/temporary-removal and Wutai transactions,
   ordinary field/battle/world-map transitions, original-avatar behavior and
   actual disc switching with Sephiroth progress intact. No new story content or
   arbitrary leader control is required.
7. Verify Crescent Arc learning/unlock and gauge/progression persistence, an
   extended-card round trip and standard export/import. Keep stronger checks for
   interrupted saving and rewind during a save, using the documented partial
   sector/recovery contract. Do not promise whole-save atomicity that the native
   multisector write path does not provide.
8. Build/check the final configuration, update Beads and acceptance records,
   commit/push to the fork and update the reviewable PRs. Leave future work
   explicitly deferred; do not call untested prototype content complete.

Where executable/overlay bytes match, execute shared behavior once and verify
guards across all three discs. Keep actual disc changes/disc-specific asset
checks. No every-item-by-every-character matrix, 16 live additions or exhaustive
map/aspect traversal is needed. Reuse passing capacity, corruption and original
code suites; expand when a new change or failure justifies it.

## Source and evidence entry points

- Registry/records: `src/ff7_party_game.c/.h`, `ff7_party.c/.h`.
- UI/inventory: `ff7_party_menu.c`, `ff7_party_resident.c`, their site tables.
- Battle/motions: `ff7_party_battle.c`, `ff7_party_motion.c`,
  `ff7_party_motion_runtime.c`; `tools/inspect_ff7_animations.py`.
- Limits: `ff7_party_limit_policy.c`, `ff7_party_limit.c/.h` and site table.
- Persistence: `ff7_party_game_save.c`, `ff7_party_projection.c`,
  `tools/ff7_save.py`. LOAD restoration must remain after native checksum success
  at `0x801D49B0`; the old earlier restore at `0x801D2134` broke valid loads.
- Core field loader/state is already integrated; it is distinct from the optional
  BF leader callback. Preserve independent entity identities/native NPCs.
- Package evidence: `mods/preloaded/packages/ff7.expanded-party/*validation.json`
  and `*evidence.json`. Oracle reports state their stubs and limits; passing
  isolated code is not a full gameplay claim.
- Local diagnostics under ignored `analysis/`: `live_debug.py`, `live_smoke.py`,
  `live_field_probe.py`, `live5_accept.py`, `check_live_save.py`, plus `live8-*`,
  `live10-*` and `live11-*` captures/reports. Inspect before reusing; some write
  diagnostic RAM/permissions and have scene-specific assumptions.

## Existing local build and test tools

PowerShell, native Windows Release/Ninja build in `build-release`, MinGW compiler
at `C:\msys64\mingw64\bin\cc.exe`; `PSX_DEBUG_TOOLS=ON`. Invoke tools directly
by absolute path to avoid MSYS/Cygwin shims interpreting Windows paths.

```powershell
Set-Location -LiteralPath 'F:\Projects\psxrecomp\Final-Fantasy-VII'
$ff7Python = 'C:\Users\Matthew\AppData\Local\Programs\Python\Python312\python.exe'
& 'C:\Program Files\CMake\bin\cmake.exe' --build build-release --parallel 4
& 'C:\Program Files\CMake\bin\ctest.exe' --test-dir build-release --output-on-failure
$env:FF7_PARTY_TEST_DLL = (Join-Path (Get-Location).Path 'analysis\ff7-party-tests.dll')
& $ff7Python -m unittest discover -s tests -p 'test_ff7_save.py'
```

These are entry points, not instructions to test stale binaries or rebuild the
optional prototype. Rebuild the parity DLL if codec source changes; skipped
parity cases do not count as passing parity. A new worktree needs its own CMake
configuration rather than reusing a cache pointing at another source directory.
Owned cues are `disc/Final Fantasy VII (USA) (Disc 1).cue` through Disc 3.

Retail oracles under `tools/test_party_*_against_retail.py` use Unicorn and a
purpose-built fixture library. The limits runner is **plural**:
`test_party_limits_against_retail.py --disc CUE --library DLL --output REPORT`.
Existing ignored fixture DLLs include `ff7_party_limit_test.dll`,
`ff7_party_menu_test.dll` and `ff7_party_game_save_test.dll`; rebuild relevant
fixtures after changing their source. Do not substitute a differently scoped DLL.

The executable is `build-release/Final_Fantasy_7.exe`. Existing live scripts use
the game's TCP debug bridge on `127.0.0.1:4397`, selectable with
`--game game.toml --debug-port 4397 --no-launcher --hidden-window`.
Use `--memcard-dir` pointing to a dedicated diagnostic directory. A hidden
presenter is needed for meaningful hardware-renderer checks; pure headless output
is not equivalent. Background launches must use `Start-Process -WindowStyle Hidden`.
Inspect current process ownership before starting/stopping anything; do not
terminate unrelated game/tool processes. The previous owned diagnostic game was
stopped on pause; this handoff did not launch one.

Save CLI example: `python tools/ff7_save.py export-standard INPUT --output NEW.mcd`.
It currently offers inspect/export, not a separate import command. Existing raw
card load/import is the accepted path. Extra characters and their held equipment/
materia are omitted by standard export without duplicating them into inventory.

## Beads and workspace rules

Use only central `F:\Software\beads\issues`; never run `bd init` in this repo.
Game epic `beads-z9df`; bootstrap/integration `beads-p389`; loading/rendering
`beads-dmfi` (priority 1); Sephiroth `beads-uyog` (priority 2). Concrete issues are
already in progress. Update the owning issue at findings/validation/integration
milestones and record branch/commit. Close only after the outcome is validated.
Use `C:\Program Files\nodejs\bd.ps1 -C F:\Software\beads\issues`.

Latest durable records contain the reduced scope and documentation checkpoint,
but their execution metadata still describes the prior pause. Update it for the
owner-authorized Claude continuation. Last Dolt push failed with error 1105 and
a missing remote Dolt ref; do not reset/repair the database as a side task.
A fresh read during this handoff did not finish and was cancelled. Avoid piling
up tracker clients; keep local milestone notes if it is temporarily unresponsive.

Honor the owner's global AGENTS instructions: native PowerShell/.NET filesystem
operations, no `cmd /c` delete/move/copy/mklink fallback, verify absolute paths
before recursive operations, never accidentally ShellExecute a file path.
Use Ghidra's automatically spawned headless MCP registry only if needed:
`registry_list filter="psx/"`, then `registry_open`; no GUI, ports or process
killing. Commit annotation JSON, never `.gpr`/`.rep`. Read
`THIRD_PARTY_ATTRIBUTION.md`: existing disassembly/address evidence is useful,
but unlicensed decompilation C is not imported. Do not restart reverse engineering
from scratch where the checked evidence already answers the question.
