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

Enhancements are independent packages in the Mods screen. All default to off.

**Internal Resolution** (`ff7.enhancement.resolution`) renders polygons at
720p, 1080p (default), 1440p or 4K. It is an integer raster scale (1080p is 5x
at 240 lines), works at the original 4:3 aspect, and does not change saved
renderer settings. `PSX_INTERNAL_RESOLUTION` still overrides it. Prerendered
field backgrounds and FMVs are original-resolution images.

**Widescreen** (`ff7.enhancement.renderer`) replaces the retired widescreen
feature. It uses psxrecomp's hardware native-wide renderer shared with Tomba,
rather than changing the guest's projection. Its one option is the aspect:
adaptive (default, follows the window) or fixed 16:9/21:9/32:9.
The world map fills the wide view: its terrain screen cull and sky quad are
widened through `[widescreen.cull]` and `[[widescreen.signed_x_bound]]` in
`game.toml`. Prerendered fields and battles keep 4:3 (fields until a verified
background tile/camera adapter exists; battle ground meshes end inside the
wide margins). FMVs and full-screen 2D use the framework's native policy.

**Smooth 3D** (`ff7.enhancement.smooth-3d`, on by default) is PGXP sub-pixel
geometry and perspective-correct texturing with CPU propagation. It never
changes guest backface decisions. It replaces the framework's generic
`psx.enhancement.pgxp`, which this title excludes. **3D Texture Filter**
(`ff7.enhancement.texture-filter`, on by default) applies stable minification to
proven 3D polygons; UI stays nearest. Both work with or without Widescreen.

**Fast Loading** (`ff7.enhancement.loading`) adds a guarded host implementation
of the original LZS decompressor. It checks the routine's instruction hash,
decodes into scratch space, and publishes RAM through the runtime's
executable-write tracking. Unsupported input runs the original code. The oracle
compares output and all 32 GPRs against the original MIPS routine on 600
generated streams, two retail assets, and seven streaming-overlap/segment-alias
cases. The mod has no options. Load pacing and native CD timing are retained:
accelerated sector bursts produced incomplete actors in the first battle.

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
