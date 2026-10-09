# Final Fantasy 7

<!-- retcomm-readme-metrics -->
[![GitHub downloads (all assets, all releases)](https://img.shields.io/github/downloads/TechnicallyComputers/Final-Fantasy-VII/total)](https://github.com/TechnicallyComputers/Final-Fantasy-VII/releases)
[![GitHub downloads (latest release)](https://img.shields.io/github/downloads/TechnicallyComputers/Final-Fantasy-VII/latest/total)](https://github.com/TechnicallyComputers/Final-Fantasy-VII/releases/latest)
[![GitHub release](https://img.shields.io/github/v/release/TechnicallyComputers/Final-Fantasy-VII)](https://github.com/TechnicallyComputers/Final-Fantasy-VII/releases/latest)
<!-- /retcomm-readme-metrics -->

<!-- retcomm-readme-boxart -->
<p align="center">
  <img src="launcher_assets/img/boxart.png" alt="Final Fantasy 7 box art" width="280">
</p>
<!-- /retcomm-readme-boxart -->

Static recompilation of **Final Fantasy 7** built on
[psxrecomp](https://github.com/mstan/psxrecomp) and
[recomp-ui](https://github.com/mstan/recomp-ui).

The Western release of Final Fantasy VII (released as Final Fantasy VII International in Japan) included additional elements and alterations, such as streamlining of the menu and Materia system, reducing the health of enemies, new visual cues to help with navigation across the world map, and additional cutscenes relating to Cloud's past.

| | |
|---|---|
| Players | 1 |
| Region | USA |
| Publisher | Square Enix |
| Year | 1997 |

Scaffolded with the New Project Layout. See
`psxrecomp/docs/GAME_PROJECT_SETUP.md` for the full flow.

<!-- retcomm-readme-launcher -->
## Retro Launcher

You can run this title **standalone** (release zip + the built-in recomp-ui
Generate & Build flow), or manage installs, updates, ROM/BIOS wiring, and queued
builds more intuitively with
**[Retro Launcher](https://github.com/RetroPortingToolKit/Retro-Launcher)** —
the Retro Compilation Manager hub for self-compiling recomps.

[Downloads](https://github.com/RetroPortingToolKit/Retro-Launcher/releases) ·
[Full README & features](https://github.com/RetroPortingToolKit/Retro-Launcher#readme)

<p align="center">
  <img src="https://raw.githubusercontent.com/RetroPortingToolKit/Retro-Launcher/main/docs/screenshots/hub-and-game-launcher.png" alt="Retro hub with a background build, next to a title’s recomp-ui launcher" width="720">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/RetroPortingToolKit/Retro-Launcher/main/docs/screenshots/queue-and-background-build.png" alt="Background cmake build with titles queued" width="720">
</p>

Retro checks for updates, rebuilds with existing build data when possible,
shares the portable toolchain used by per-title launchers, and automates
BIOS/ROM/save plumbing so you are not stuck repeating each game’s wizard by hand.
<!-- /retcomm-readme-launcher -->

## Symbols and source-level modding

The recompiled C is generated from the disc, so out of the box every function
is named `func_800257CC`. `symbols.toml` and `symbols_overlays.toml` put names
back on ~1,100 of them, imported from the
[ff7-decomp](https://github.com/Xeeynamo/ff7-decomp) symbol map by Xeeynamo and
contributors — see `THIRD_PARTY_ATTRIBUTION.md` for provenance, licence status,
and what may and may not be taken from that project. **Their source is not used
here and must not be merged**; only the address tables were read.

```sh
python3 tools/import_decomp_symbols.py                    # refresh from the pinned commit
python3 tools/import_decomp_symbols.py --verify-generated  # corroborate against our own codegen
python3 tools/sync_symbols.py                             # maps -> psx_symbols.h
python3 tools/sync_symbols.py --check-hooks               # game.toml agrees with the map
```

Host and mod code addresses functions by name — `PSX_FN_SetupGamepad`, not a
hex literal. Setting `hook = true` on an entry makes the recompiler emit a
`psx_mod_function_entry()` call at that function; `src/ff7_mods.c` registers
trusted plugin callbacks against them, and `game.toml`'s address list is
derived from the map rather than hand-maintained.

Imported names are `status = "contextual"` — evidence-backed but **not verified
by us**. The default-off *Hook Trace (developer)* feature in the Mods list is
how you promote one: arm it, do the thing the name claims to describe, and see
whether the call fires.

## Enhancement mods

Enhancements are independently selectable packages in the Mods screen and
default to off. The original widescreen feature has been retired in favor of
**Enhanced Renderer** (`ff7.enhancement.renderer`). It uses psxrecomp's hardware
native-wide renderer shared with Tomba, rather than changing the guest's
projection. Options include adaptive window aspect, fixed 16:9/21:9/32:9,
1080p (default) through 4K, PGXP geometry/texture precision, and stable texture
minification. The primary executable includes PGXP propagation; activating the
mod requests it without changing guest backface decisions or saved settings.
Resolution is an integer raster scale (1080p requests 5x at 240 lines), subject
to the backend and the player's dynamic-resolution policy.

This renderer package is experimental. Prerendered fields retain 4:3 until a
verified background tile/camera adapter is available. FMVs and full-screen 2D
use the framework's native presentation policy. Battle/world geometry outside
the original frame still needs coverage and culling validation.

**Fast Loading** (`ff7.enhancement.loading`) adds a guarded host implementation
of the original LZS decompressor and accelerates host pacing during CD loads.
It checks the complete routine's instruction hash, decodes into scratch space,
and publishes RAM through the runtime's executable-write tracking. Unsupported
input retains the original code. The oracle compares output and all 32 GPRs
against the original MIPS routine on 600 generated streams, two retail assets,
and seven streaming-overlap/segment-alias cases, including the observed startup
call. Overlapping guest input reads observe previous output stores, matching
the original routine even when it overwrites unread compressed bytes.
Native CD timing is retained: accelerated sector bursts produced incomplete
actors in the first battle. Gzip overlays and other loaders still execute their original
code; eliminating all loading is an ongoing task.

**Expanded Party Research** (`ff7.expanded-party`) is developer-only groundwork,
not a playable Sephiroth mod. `src/ff7_party.c` provides independent character
records and IDs, an always-unlocked Sephiroth initializer from the owner's
original kernel template, and a versioned extension appended after a standard
128 KiB memory card. The developer-only **Extended card persistence** feature
(`party-save`) connects the codec to the framework's card transport: it loads
and refreshes existing valid metadata, while raw cards remain raw. It does not
create characters or populate metadata from gameplay. Native base bytes are
unchanged by this adapter; all extra state is bound to the whole card digest.
Tests cover coexistence with Cloud/Vincent, storage isolation, corrupt/stale
metadata, transactional decoding and adapter reload/flush behavior.

Export a standard card with an explicit new output path:

```sh
python tools/ff7_save.py export-standard "saves/extended.mcd" --output "saves/standard-copy.mcd"
```

Export preserves the standard base byte for byte and omits extra characters;
it never interprets Sephiroth as Vincent or overwrites the source. See
[the save-format writeup](docs/SEPHIROTH_SAVE_FORMAT.md) for layout, validation,
recovery and native fallback-party requirements. Gameplay slot-save/load hooks,
fallback roster projection, rewind synchronization, PHS selection, menu/battle
accessors, actor-scoped AI control and complete animations remain unfinished.

The developer-only **Independent record queries** feature (`party-access`)
provides guarded name and equipment materia-slot access for explicitly published
16-bit extra identities. It allocates separate Expansion 1 records, leaves
ordinary callers and flashback ID 10 stock, and invalidates publication after
savestate restore. It does not yet convert the game's PHS/menu/battle callers.
The calling convention and publication/snapshot API are documented in
`src/ff7_party_access.h`; exact guards and remaining sites are recorded in
`access.evidence.json` beside the package. An original-MIPS oracle checks all
32 registers and the return address behavior of the three query functions.

Read-only evidence tools inspect all three original discs without downloading
decompilation source or distributing assets:

```sh
python tools/inspect_ff7_party.py "disc/Final Fantasy VII (USA) (Disc 1).cue"
python tools/inspect_ff7_animations.py "disc/Final Fantasy VII (USA) (Disc 1).cue"
python -m unittest discover -s tests -p 'test_ff7_animations.py'
ctest --test-dir build-release -R ff7_party --output-on-failure
```

Set `FF7_TEST_CUE` to an owned disc's cue path to include asset-based animation
tests. `inspect_ff7_animations.py --prepare-fallbacks analysis/<directory>`
can prepare local review candidates using Sephiroth's existing motions. They
are never installed automatically and still need battle playback and loader
allocation validation. Instruction evidence lives beside the research package
in `party.evidence.json` and `animation.evidence.json`.

To reproduce the LZS oracle, install Unicorn and build `src/ff7_lzs.c` as a
shared library, then run:

```sh
python tools/test_lzs_against_retail.py --library <shared-library> \
  --disc "disc/Final Fantasy VII (USA) (Disc 1).cue"
```

## Legal

You must own the original game. Disc images under `disc/` are gitignored and
must never be committed. Retail BIOS dumps are not redistributed; OpenBIOS is
used for Generate unless you supply your own SCPH locally.

Default app icon: `assets/psxrecomp.ico` (and `.png` / `.svg`) — Retro-themed controller mark from `psxrecomp/assets/`. Windows builds embed it via `APP_ICON`.

Optional box art under `launcher_assets/img/` may come from
[libretro-thumbnails](https://github.com/libretro-thumbnails/libretro-thumbnails)
(`Named_Boxarts`); see `BOXART_SOURCE.txt` when present.

## Quick start (dev)

```bash
git submodule update --init --recursive
./psxrecomp/tools/ci/build_emitters.sh
python3 psxrecomp/psxrecomp_cli.py generate \
  --config game.toml --project-root . --disc disc/<your>.cue
cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-release --target psx-runtime
```

Zip prefix for CI artifacts: `finalfantasy7`.

## Symbols

Progressive map: `symbols.toml` → `python3 tools/sync_symbols.py` →
`psx_symbols.h` (`PSX_FN_*`). See `psxrecomp/docs/SYMBOLS.md`.

## Framework pins

Submodule gitlinks (`psxrecomp`, optional `recomp-ui`, nested `recomp-net`)
are authoritative. `framework_pins.txt` is an optional scaffold snapshot;
release CI logs SHAs with `record_pins.sh` but builds whatever the gitlinks
resolve to. Bump submodules deliberately — do not float on `main`/`master`
in release CI.

<!-- retcomm-readme-raid -->
---

<p align="center">
  <sub><b>R.A.I.D. — Retro AI Development</b> · a Discord for AI-assisted retro reverse-engineering, decomp &amp; recomp</sub>
</p>

<p align="center">
  <a href="https://discord.gg/Ad9BwSzctP"><img src=".github/raid-discord.png" alt="Join the Retro AI Development (R.A.I.D.) Discord" width="200"></a>
</p>
<!-- /retcomm-readme-raid -->
