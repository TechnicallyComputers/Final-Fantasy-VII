#!/usr/bin/env python3
"""Import function/data names from the Xeeynamo/ff7-decomp symbol map.

WHAT THIS DOES AND WHY IT IS ALLOWED
------------------------------------
ff7-decomp carries NO LICENSE FILE (GitHub reports `license: null`), so no
licence is granted and its *source* may not be merged. recomp-ai-rules/
LICENSING.md §5 covers exactly this case: a decomp is a read-only reference
whose useful output is "symbols and structural understanding", and §2 records
that facts — here, addresses — are not protected expression.

So this tool reads ONLY `config/*.txt` and `config/us.yaml`: address tables of
the form `name = 0x800257CC;`. It never fetches, opens, or transcribes anything
under `src/`. That restriction is enforced structurally in `_fetch()` rather
than by discipline, so a future edit cannot quietly widen it.

Every imported entry is tagged `status = "contextual"` per §5 ("Tag every
imported symbol with its provenance level ... and keep that tag in your
config"). A contextual name is evidence-backed but unverified by us; it must
never later be cited as evidence.

IDENTITY GATE (§5, "Gate imports on identity")
----------------------------------------------
The decomp pins the SHA-1 of every image it targets. This tool refuses to
import unless the decomp's `main` overlay SHA-1 equals the SHA-1 of our own
`disc/SCUS_941.63`. They currently match exactly
(a95e8b16b97071203b953bb81a33980509262f30), which is why every address below
is directly valid in our address space with no rebasing.

OVERLAY SCOPING
---------------
FF7 loads most overlays at the SAME address: battle/brom/dschange/ending/
field/world all at 0x800A0000, the four menus at 0x801D0000, batini/barrier/
lv5deth at 0x801B0000. A flat pc->name map is therefore only valid for `main`.
Main-range symbols go to symbols.toml; everything else goes to
symbols_overlays.toml carrying an `overlay` key, and is macro-namespaced by
overlay so six different functions cannot claim one `func_800A0000` alias.

Usage (from game repo root):
  python3 tools/import_decomp_symbols.py            # fetch pinned commit, write
  python3 tools/import_decomp_symbols.py --check    # CI: exit 1 if out of date
  python3 tools/import_decomp_symbols.py --from-clone ../ff7-decomp
  python3 tools/import_decomp_symbols.py --dry-run  # report, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys
import urllib.error
import urllib.request

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    print("error: need Python 3.11+ (tomllib)", file=sys.stderr)
    raise SystemExit(2)

# --- The pin -----------------------------------------------------------------
# LICENSING.md §5: "Record the exact commit and licence status of any reference
# you consult, before you consult it." Bump deliberately, never automatically —
# a moving reference silently changes names you have already cited.
DECOMP_REPO = "Xeeynamo/ff7-decomp"
DECOMP_COMMIT = "24a46a990dccc7dad4cac107408df00b0cac6c4c"  # 2026-08-27
DECOMP_LICENSE = "NONE — no LICENSE file; all rights reserved (read-only ref)"
RAW = "https://raw.githubusercontent.com/{repo}/{commit}/{path}"

# The only directory this tool may ever read. See module docstring.
ALLOWED_PREFIX = "config/"

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME_EXE = ROOT / "disc" / "SCUS_941.63"
SYMBOLS_PATH = ROOT / "symbols.toml"
OVERLAY_SYMBOLS_PATH = ROOT / "symbols_overlays.toml"

# Main's ALWAYS-RESIDENT region. The lower bound is game.toml load_address.
# The upper bound is NOT load_address + text_size: main's .data/.bss sit above
# .text and are just as resident and just as unambiguous — that is where the
# game-state globals a modder actually wants live (g_AccessoryTable,
# g_FieldMusicLock, g_WindowCount, ...). The real boundary is the lowest
# address any overlay loads at, which we derive from the decomp's own us.yaml
# rather than hardcode.
MAIN_BASE = 0x80010000

# `sym_export.us.txt` / `sym_export_battle.us.txt` are referenced by us.yaml but
# are BUILD ARTIFACTS (us.yaml: generated_sym_path: build/us) and are not in the
# repository. `sym_ovl_export.us.txt` is committed but referenced by no overlay,
# so its overlay-space addresses cannot be attributed unambiguously — skipped.
SKIP_FILES = {
    "config/sym_export.us.txt",
    "config/sym_export_battle.us.txt",
    "config/sym_ovl_export.us.txt",
}

# Names the decomp generates from an address carry no information we don't
# already have; importing them would just re-encode the hex.
AUTOGEN_NAME = re.compile(r"^(func|D|jtbl|_D|jpt|L)_[0-9A-Fa-f]{6,8}(_\d+)?$")
SYMBOL_LINE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(0[xX][0-9A-Fa-f]+)\s*;"
)
C_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ImportError_(RuntimeError):
    pass


# --- Fetching ----------------------------------------------------------------

def _guard(path: str) -> None:
    """Structural refusal to read anything but the address tables.

    This is the licence boundary. `src/` holds decompiled C under no licence;
    this tool must not be able to reach it even by accident.
    """
    norm = path.replace("\\", "/").lstrip("./")
    if ".." in norm.split("/"):
        raise ImportError_(f"refusing traversal path: {path!r}")
    if not norm.startswith(ALLOWED_PREFIX):
        raise ImportError_(
            f"refusing to read {path!r}: this tool may only read "
            f"{ALLOWED_PREFIX}* from {DECOMP_REPO}. The decomp has no licence; "
            "its source may not be merged (LICENSING.md §5)."
        )


class Source:
    """Either the pinned upstream commit or a local clone of it."""

    def __init__(self, clone: pathlib.Path | None):
        self.clone = clone

    def label(self) -> str:
        return str(self.clone) if self.clone else f"{DECOMP_REPO}@{DECOMP_COMMIT[:12]}"

    def fetch(self, path: str) -> str | None:
        _guard(path)
        if self.clone is not None:
            f = self.clone / path
            return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else None
        url = RAW.format(repo=DECOMP_REPO, commit=DECOMP_COMMIT, path=path)
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise ImportError_(f"fetch {path}: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise ImportError_(
                f"fetch {path}: {e.reason}. Offline? Use --from-clone <path>."
            ) from e


# --- us.yaml: overlays, their load addresses, and the identity gate -----------

def parse_overlays(text: str) -> list[dict]:
    """Return [{name, sha1, vram_start, symbol_files}] from the decomp config.

    PyYAML when present; otherwise a targeted line parser. The pin is what makes
    the fallback safe — the file cannot change shape under us without a
    deliberate DECOMP_COMMIT bump.
    """
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(text)
        out = []
        for ov in doc.get("overlays", []) or []:
            paths = ov.get("symbol_addrs_path") or []
            out.append({
                "name": str(ov["name"]),
                "sha1": str(ov.get("sha1", "")).lower(),
                "vram_start": int(str(ov.get("vram_start", "0")), 0),
                "symbol_files": [str(p) for p in paths],
            })
        return out
    except ModuleNotFoundError:
        pass

    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^\s*-\s+name:\s*(\S+)", line)
        if m:
            cur = {"name": m.group(1), "sha1": "", "vram_start": 0, "symbol_files": []}
            out.append(cur)
            continue
        if cur is None:
            continue
        if m := re.match(r"^\s*sha1:\s*([0-9A-Fa-f]{40})", line):
            cur["sha1"] = m.group(1).lower()
        elif m := re.match(r"^\s*vram_start:\s*(0[xX][0-9A-Fa-f]+)", line):
            cur["vram_start"] = int(m.group(1), 0)
        elif m := re.match(r"^\s*-\s+(config/\S+\.txt)\s*$", line):
            cur["symbol_files"].append(m.group(1))
    return out


def verify_identity(overlays: list[dict]) -> str:
    """§5: abort unless the reference targets OUR exact executable."""
    main = next((o for o in overlays if o["name"] == "main"), None)
    if main is None or not main["sha1"]:
        raise ImportError_("us.yaml has no `main` overlay SHA-1 — cannot gate import")
    if not GAME_EXE.is_file():
        raise ImportError_(
            f"missing {GAME_EXE} — the identity gate needs our own boot EXE. "
            "Run the disc prepare step first."
        )
    ours = hashlib.sha1(GAME_EXE.read_bytes()).hexdigest()
    if ours != main["sha1"]:
        raise ImportError_(
            "IDENTITY GATE FAILED — refusing to import.\n"
            f"  ours ({GAME_EXE.name}): {ours}\n"
            f"  decomp `main` target:   {main['sha1']}\n"
            "Every address in that map would be a guess against a different "
            "build. Nothing was written."
        )
    return ours


# --- Symbol tables -----------------------------------------------------------

def parse_symbols(text: str) -> list[tuple[str, int]]:
    """`name = 0xADDR;` lines. Commented-out entries are the decomp's own
    'not confident' marker and are deliberately not imported."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith(("//", "#")):
            continue
        m = SYMBOL_LINE.match(line)
        if not m:
            continue
        name, addr = m.group(1), int(m.group(2), 0)
        if AUTOGEN_NAME.match(name) or not C_IDENT.match(name):
            continue
        out.append((name, addr & 0xFFFFFFFF))
    return out


def main_end(overlays: list[dict]) -> int:
    """Lowest address any overlay loads at — the top of main's resident region."""
    starts = [o["vram_start"] for o in overlays
              if o["name"] != "main" and o["vram_start"] > MAIN_BASE]
    if not starts:
        raise ImportError_("no overlay load addresses in us.yaml — cannot bound main")
    return min(starts)


def collect(src: Source, overlays: list[dict]) -> tuple[dict, dict, list[str]]:
    """-> (main {pc: name}, overlay {(ov, pc): name}, warnings)."""
    MAIN_END = main_end(overlays)
    file_owner: dict[str, str] = {}
    ambiguous: set[str] = set()
    for ov in overlays:
        for f in ov["symbol_files"]:
            if f in SKIP_FILES:
                continue
            if file_owner.setdefault(f, ov["name"]) != ov["name"]:
                ambiguous.add(f)

    main: dict[int, str] = {}
    ovl: dict[tuple[str, int], str] = {}
    warn: list[str] = []
    for f in ambiguous:
        warn.append(f"{f}: referenced by multiple overlays — overlay-space "
                    f"symbols from it were skipped as unattributable")

    for path in sorted(file_owner):
        text = src.fetch(path)
        if text is None:
            warn.append(f"{path}: not present at this pin (generated at build time?) — skipped")
            continue
        owner = file_owner[path]
        for name, pc in parse_symbols(text):
            if MAIN_BASE <= pc < MAIN_END:
                # A main-range address in an overlay's file is that overlay
                # calling back into the always-resident executable.
                if main.setdefault(pc, name) != name:
                    warn.append(f"main 0x{pc:08X}: {main[pc]!r} vs {name!r} — kept first")
            elif pc < MAIN_BASE:
                warn.append(f"{path}: {name} = 0x{pc:08X} is below load address "
                            "(BIOS/kernel space) — skipped")
            elif path in ambiguous:
                continue
            elif owner == "main":
                # main's own file naming an address in overlay RAM. Which overlay
                # owns it is unproven, and inventing an attribution would make a
                # guess citable as a fact. Skip honestly.
                warn.append(f"{path}: {name} = 0x{pc:08X} is in overlay space but "
                            "owned by `main` — unattributable, skipped")
            else:
                if ovl.setdefault((owner, pc), name) != name:
                    warn.append(f"{owner} 0x{pc:08X}: {ovl[(owner, pc)]!r} vs {name!r} — kept first")
    return main, ovl, warn


# --- Writing -----------------------------------------------------------------

BANNER = """\
# {title}
#
# PARTLY IMPORTED — DO NOT HAND-EDIT THE IMPORTED BLOCK.
# Regenerate with: python3 tools/import_decomp_symbols.py
#
# Names below marked status = "contextual" were imported from the symbol map of
# {repo}
#   commit:  {commit}
#   licence: {licence}
#
# That project's SOURCE is not used here and must not be merged: with no LICENCE
# file, no licence is granted (recomp-ai-rules/LICENSING.md §5). Only the address
# tables under config/ were read — addresses are facts, not expression (§2).
# Import is gated on SHA-1 identity with our own disc/SCUS_941.63:
#   {sha1}
#
# "contextual" means evidence-backed but UNVERIFIED BY US. Per §5 a contextual
# name must never later be cited as evidence. Promote to "confirmed" only after
# you have independently established the behaviour, and move the entry into the
# hand-authored block above so the next import cannot overwrite your work.
#
# Attribution: THIRD_PARTY_ATTRIBUTION.md
"""

MARK_BEGIN = "# >>> BEGIN IMPORTED (ff7-decomp) — regenerated, do not hand-edit"
MARK_END = "# <<< END IMPORTED (ff7-decomp)"


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def split_manual(path: pathlib.Path) -> str:
    """Everything before the imported block: the hand-authored entries, kept
    verbatim. A rerun must never destroy work someone typed."""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    return text.split(MARK_BEGIN)[0].rstrip("\n") if MARK_BEGIN in text else text.rstrip("\n")


def manual_pcs(path: pathlib.Path) -> set[int]:
    if not path.is_file():
        return set()
    head = split_manual(path)
    try:
        data = tomllib.loads(head)
    except tomllib.TOMLDecodeError:
        return set()
    pcs = set()
    for raw in data.get("func", []):
        v = raw.get("pc")
        pcs.add(int(v, 0) if isinstance(v, str) else int(v))
    return pcs


def render_main(main: dict[int, str], keep: set[int], sha1: str) -> str:
    head = split_manual(SYMBOLS_PATH)
    lines = [head, "", MARK_BEGIN, ""]
    lines.append(BANNER.format(
        title="Imported main-executable symbols (always resident).",
        repo=DECOMP_REPO, commit=DECOMP_COMMIT, licence=DECOMP_LICENSE, sha1=sha1,
    ))
    n = 0
    for pc in sorted(main):
        if pc in keep:  # a hand-authored entry already owns this address
            continue
        lines += [
            "[[func]]",
            f"pc = 0x{pc:08X}",
            f'name = "{esc(main[pc])}"',
            "emit = false",
            'status = "contextual"',
            f'note = "ff7-decomp {DECOMP_COMMIT[:12]} (main)"',
            "",
        ]
        n += 1
    lines.append(f"# {n} imported entries.")
    lines.append(MARK_END)
    return "\n".join(lines) + "\n"


def render_overlays(ovl: dict[tuple[str, int], str], overlays: list[dict], sha1: str) -> str:
    base = {o["name"]: o["vram_start"] for o in overlays}
    lines = [BANNER.format(
        title="Imported OVERLAY symbols — scoped, because FF7 overlays collide.",
        repo=DECOMP_REPO, commit=DECOMP_COMMIT, licence=DECOMP_LICENSE, sha1=sha1,
    )]
    lines += [
        "# Most FF7 overlays share a load address (battle/brom/dschange/ending/",
        "# field/world at 0x800A0000; the menus at 0x801D0000; batini/barrier/",
        "# lv5deth at 0x801B0000), so a flat pc -> name map is WRONG here. Each",
        "# entry carries `overlay`, and tools/sync_symbols.py namespaces the macro",
        "# as PSX_FN_<OVERLAY>_<name> with no bare func_<pc> alias.",
        "#",
        "# These addresses live in overlay space and are NOT present in the static",
        "# generated/ tree, which covers the main executable only. They apply to",
        "# code reached through the overlay cache (psxrecomp/docs/COMPILING_OVERLAYS.md).",
        "",
        "# Load addresses, so offset math does not have to be rediscovered. Note how",
        "# many share one base — that is the whole reason these are scoped.",
    ]
    for o in sorted(overlays, key=lambda o: (o["vram_start"], o["name"])):
        if o["name"] == "main":
            continue
        lines += [
            "[[overlay]]",
            f'name = "{esc(o["name"])}"',
            f"base = 0x{o['vram_start']:08X}",
            "",
        ]
    for ov_name, pc in sorted(ovl, key=lambda k: (k[0], k[1])):
        lines += [
            "[[func]]",
            f'overlay = "{esc(ov_name)}"',
            f"pc = 0x{pc:08X}",
            f'name = "{esc(ovl[(ov_name, pc)])}"',
            f"# load base 0x{base.get(ov_name, 0):08X}, offset +0x{pc - base.get(ov_name, 0):X}",
            "emit = false",
            'status = "contextual"',
            f'note = "ff7-decomp {DECOMP_COMMIT[:12]} ({ov_name})"',
            "",
        ]
    lines.append(f"# {len(ovl)} imported entries.")
    return "\n".join(lines) + "\n"


# --- Corroboration against our own recompilation -----------------------------

GEN_DEF = re.compile(r"^\s*void\s+func_([0-9A-Fa-f]{8})\s*\(\s*CPUState\s*\*", re.M)


def generated_entries() -> set[int]:
    """Function entry addresses OUR recompiler independently proved from the
    image. Nothing here comes from the decomp."""
    out: set[int] = set()
    gen = ROOT / "generated"
    if not gen.is_dir():
        return out
    for f in sorted(gen.glob("*.c")):
        out.update(int(m, 16) for m in GEN_DEF.findall(f.read_text(
            encoding="utf-8", errors="replace")))
    return out


def verify(main_syms: dict[int, str]) -> int:
    """Do the imported names land where we independently found functions?

    PRINCIPLES.md "Tool Skepticism", and LICENSING.md §5's "prove a reference
    before trusting its labels". This corroborates BOUNDARIES only. A name
    landing on a real function entry means both projects agree code starts
    there — it says nothing about whether the name is correct, so entries stay
    status = "contextual" either way. Only observed behaviour promotes a name.
    """
    entries = generated_entries()
    if not entries:
        print("generated/ is absent or empty — nothing to corroborate against.",
              file=sys.stderr)
        print("Generate the game C first; this check is not a licence gate.",
              file=sys.stderr)
        return 1

    on_entry, data_like, unmatched = [], [], []
    for pc, name in sorted(main_syms.items()):
        if pc in entries:
            on_entry.append((pc, name))
        elif name.startswith(("g_", "D_")):
            data_like.append((pc, name))
        else:
            unmatched.append((pc, name))

    total = len(main_syms)
    print(f"our recompiler proved {len(entries)} function entries in generated/")
    print(f"imported main symbols: {total}")
    print(f"  on a proven function entry : {len(on_entry)} "
          f"({100.0 * len(on_entry) / total:.1f}%)  <- boundary corroborated")
    print(f"  g_*-style data names       : {len(data_like)} "
          "(expected NOT to be function entries)")
    print(f"  neither                    : {len(unmatched)}")
    if unmatched:
        print("\n  Not on any entry we proved. Each is either data we did not")
        print("  classify, or a function our static pass never reached — the")
        print("  latter are candidates for seeds/ghidra_funcs.txt. A hook on")
        print("  one of these would silently never fire.")
        for pc, name in unmatched[:15]:
            print(f"    0x{pc:08X}  {name}")
        if len(unmatched) > 15:
            print(f"    ... and {len(unmatched) - 15} more")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if either file would change (CI drift gate)")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--verify-generated", action="store_true",
                    help="corroborate imported addresses against the function "
                         "entries our own recompiler proved (writes nothing)")
    ap.add_argument("--from-clone", type=pathlib.Path, default=None,
                    help="read config/ from a local ff7-decomp clone instead of the network")
    args = ap.parse_args()

    src = Source(args.from_clone)
    try:
        us_yaml = src.fetch("config/us.yaml")
        if us_yaml is None:
            raise ImportError_(f"config/us.yaml not found at {src.label()}")
        overlays = parse_overlays(us_yaml)
        if not any(o["name"] == "main" for o in overlays):
            raise ImportError_("parsed no `main` overlay from us.yaml — aborting")
        sha1 = verify_identity(overlays)
        boundary = main_end(overlays)
        main_syms, ovl_syms, warns = collect(src, overlays)
    except ImportError_ as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"source:   {src.label()}")
    print(f"licence:  {DECOMP_LICENSE}")
    print(f"identity: {sha1} ✓ (disc/SCUS_941.63 == decomp `main`)")
    print(f"main region: 0x{MAIN_BASE:08X}..0x{boundary:08X} "
          "(to the lowest overlay load address)")
    print(f"parsed:   {len(main_syms)} main, {len(ovl_syms)} overlay "
          f"({len({o for o, _ in ovl_syms})} overlays)")
    for w in warns:
        print(f"  warn: {w}")

    if args.verify_generated:
        return verify(main_syms)

    keep = manual_pcs(SYMBOLS_PATH)
    shadowed = sorted(keep & set(main_syms))
    for pc in shadowed:
        print(f"  keep: 0x{pc:08X} hand-authored entry wins over "
              f"imported {main_syms[pc]!r}")

    new_main = render_main(main_syms, keep, sha1)
    new_ovl = render_overlays(ovl_syms, overlays, sha1)

    if args.check:
        stale = [p for p, t in ((SYMBOLS_PATH, new_main), (OVERLAY_SYMBOLS_PATH, new_ovl))
                 if not p.is_file() or p.read_text(encoding="utf-8") != t]
        for p in stale:
            print(f"out of date: {p}", file=sys.stderr)
        return 1 if stale else 0

    if args.dry_run:
        print("dry-run: nothing written")
        return 0

    SYMBOLS_PATH.write_text(new_main, encoding="utf-8")
    OVERLAY_SYMBOLS_PATH.write_text(new_ovl, encoding="utf-8")
    print(f"wrote {SYMBOLS_PATH} and {OVERLAY_SYMBOLS_PATH}")
    print("next: python3 tools/sync_symbols.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
