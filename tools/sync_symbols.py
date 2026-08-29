#!/usr/bin/env python3
"""Sync symbol maps → psx_symbols.h / psx_symbols_overlays.h (PSX_FN_* macros).

Progressive naming for PSX titles (partial decomp). Catalog freely; set
emit=true only when an entry is safe for AOT / host hooks.

Two maps, because FF7's overlays collide:

  symbols.toml           always-resident main executable. Flat pc -> name, so
                         each entry gets both PSX_FN_<name> and the bare
                         func_<pc> alias the generated tree uses.
  symbols_overlays.toml  overlay code. battle/brom/dschange/ending/field/world
                         ALL load at 0x800A0000, the menus share 0x801D0000,
                         and batini/barrier/lv5deth share 0x801B0000 — so a
                         bare func_<pc> alias would be a lie. These get
                         PSX_FN_<OVERLAY>_<name> and no alias.

`hook = true` marks a function whose entry a trusted mod plugin wants to
observe. The recompiler emits the psx_mod_function_entry() call site from
game.toml's [recompiler] mod_function_entry_funcs list; --check-hooks verifies
that hex list still agrees with this named map, so host hooks never drift back
into raw hex (psxrecomp/docs/SYMBOLS.md).

Usage (from game repo root):
  python3 tools/sync_symbols.py
  python3 tools/sync_symbols.py --check         # CI: headers up to date?
  python3 tools/sync_symbols.py --check-hooks   # CI: game.toml agrees?
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        print("error: need Python 3.11+ tomllib or pip install tomli", file=sys.stderr)
        raise SystemExit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYMBOLS_PATH = ROOT / "symbols.toml"
OVERLAY_SYMBOLS_PATH = ROOT / "symbols_overlays.toml"
HEADER_PATH = ROOT / "psx_symbols.h"
OVERLAY_HEADER_PATH = ROOT / "psx_symbols_overlays.h"
GAME_TOML_PATH = ROOT / "game.toml"

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# LICENSING.md §5 tags provenance as guessed | contextual | confirmed. `hot` is
# psxrecomp's own performance marker and is accepted alongside them.
KNOWN_STATUS = {"guessed", "contextual", "confirmed", "hot"}


def game_title(symbols_path: pathlib.Path) -> str:
    """Label for the header comment.

    Read from game.toml rather than the containing directory's name: the
    generated headers are committed and CI diffs them, so a label derived from
    the checkout path makes `--check` fail for anyone whose clone is not named
    exactly like the repository (and inside a git worktree, which is how the
    gate itself is best verified).
    """
    cfg = symbols_path.parent / "game.toml"
    if cfg.is_file():
        try:
            name = tomllib.loads(cfg.read_text(encoding="utf-8")).get(
                "game", {}).get("name")
        except tomllib.TOMLDecodeError:
            name = None
        if name:
            return str(name)
    return symbols_path.parent.name


def _parse_int(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise TypeError(f"expected int, got {type(value)!r}")


def _load(path: pathlib.Path, *, scoped: bool) -> list[dict]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    funcs = []
    for raw in data.get("func", []):
        pc = _parse_int(raw["pc"]) & 0xFFFFFFFF
        name = str(raw["name"])
        if not IDENT.fullmatch(name):
            raise SystemExit(f"{path.name}: invalid func name {name!r} (need C identifier)")
        status = str(raw.get("status", "guessed"))
        if status not in KNOWN_STATUS:
            raise SystemExit(
                f"{path.name}: 0x{pc:08X} has status {status!r}; "
                f"expected one of {sorted(KNOWN_STATUS)}"
            )
        entry = {
            "pc": pc,
            "name": name,
            "emit": bool(raw.get("emit", False)),
            "hook": bool(raw.get("hook", False)),
            "status": status,
            "note": str(raw.get("note", "")),
        }
        if scoped:
            overlay = str(raw.get("overlay", ""))
            if not IDENT.fullmatch(overlay):
                raise SystemExit(
                    f"{path.name}: 0x{pc:08X} ({name}) has no valid `overlay`. "
                    "Overlay symbols MUST be scoped — several FF7 overlays share "
                    "a load address, so an unscoped entry is ambiguous."
                )
            entry["overlay"] = overlay
        funcs.append(entry)
    return funcs


def _check_collisions(funcs: list[dict], *, path: pathlib.Path, scoped: bool) -> None:
    """A duplicate pc or name silently produces conflicting #defines — a
    redefinition the compiler resolves last-wins. Fail loudly instead."""
    by_pc: dict[tuple, dict] = {}
    by_name: dict[tuple, dict] = {}
    errs: list[str] = []
    for f in funcs:
        scope = f.get("overlay", "") if scoped else ""
        pk, nk = (scope, f["pc"]), (scope, f["name"])
        if (prev := by_pc.get(pk)) is not None:
            where = f"{scope} " if scope else ""
            errs.append(f"  {where}0x{f['pc']:08X} named both "
                        f"{prev['name']!r} and {f['name']!r}")
        else:
            by_pc[pk] = f
        if (prev := by_name.get(nk)) is not None:
            where = f"{scope} " if scope else ""
            errs.append(f"  {where}{f['name']!r} maps to both "
                        f"0x{prev['pc']:08X} and 0x{f['pc']:08X}")
        else:
            by_name[nk] = f
    if errs:
        raise SystemExit(f"{path.name}: symbol collisions\n" + "\n".join(sorted(set(errs))))


def load_funcs(path: pathlib.Path) -> list[dict]:
    funcs = _load(path, scoped=False)
    _check_collisions(funcs, path=path, scoped=False)
    funcs.sort(key=lambda f: f["pc"])
    return funcs


def load_overlay_funcs(path: pathlib.Path) -> tuple[list[dict], list[dict]]:
    if not path.is_file():
        return [], []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    bases = [{"name": str(o["name"]), "base": _parse_int(o["base"]) & 0xFFFFFFFF}
             for o in data.get("overlay", [])]
    funcs = _load(path, scoped=True)
    _check_collisions(funcs, path=path, scoped=True)
    funcs.sort(key=lambda f: (f["overlay"], f["pc"]))
    return funcs, bases


def declared_hooks(funcs: list[dict]) -> list[dict]:
    return [f for f in funcs if f["hook"]]


def render_header(funcs: list[dict], *, game: str) -> str:
    lines = [
        "/* Auto-generated by tools/sync_symbols.py — do not edit.",
        f" * Source: symbols.toml ({game})",
        " * Progressive symbols: discover → label → manipulate via PSX_FN_*.",
        " */",
        "#pragma once",
        "",
    ]
    for f in funcs:
        note = f["note"].replace("*/", "* /")
        lines.append(
            f"/* {f['status']}: {note} */" if note else f"/* {f['status']} */"
        )
        lines.append(f"#define PSX_FN_{f['name']} 0x{f['pc']:08X}u")
        lines.append(f"#define func_{f['pc']:08X} {f['name']}  /* alias */")
        if f["emit"]:
            lines.append(f"/* emit=true — promote in recompiler/map when ready */")
        if f["hook"]:
            lines.append("/* hook=true — listed in game.toml mod_function_entry_funcs */")
        lines.append("")
    if not funcs:
        lines.append("/* (no [[func]] entries yet) */")
        lines.append("")

    hooks = declared_hooks(funcs)
    lines += [
        "/* Functions marked hook = true in symbols.toml. The recompiler emits a",
        " * psx_mod_function_entry() call at each of these, driven by game.toml",
        " * [recompiler] mod_function_entry_funcs — keep the two in agreement with",
        " * `tools/sync_symbols.py --check-hooks`.",
        " *",
        " * Iterate them by name instead of hand-listing addresses:",
        " *   #define REG(name, addr) \\",
        " *       psx_mod_register_function_entry_plugin(\"id\", addr, cb);",
        " *   PSX_FN_HOOK_LIST(REG)",
        " */",
        f"#define PSX_FN_HOOK_COUNT {len(hooks)}",
    ]
    if hooks:
        lines.append("#define PSX_FN_HOOK_LIST(X) \\")
        for i, f in enumerate(hooks):
            cont = " \\" if i + 1 < len(hooks) else ""
            lines.append(f"    X({f['name']}, 0x{f['pc']:08X}u){cont}")
    else:
        lines.append("#define PSX_FN_HOOK_LIST(X) /* none */")
    lines.append("")
    return "\n".join(lines)


def render_overlay_header(funcs: list[dict], bases: list[dict], *, game: str) -> str:
    lines = [
        "/* Auto-generated by tools/sync_symbols.py — do not edit.",
        f" * Source: symbols_overlays.toml ({game})",
        " *",
        " * Overlay symbols are SCOPED. Most FF7 overlays share a load address",
        " * (battle/brom/dschange/ending/field/world at 0x800A0000; the menus at",
        " * 0x801D0000; batini/barrier/lv5deth at 0x801B0000), so one address means",
        " * different things depending on what is resident. There is deliberately no",
        " * bare func_<pc> alias here — it could not be unambiguous.",
        " *",
        " * These addresses are NOT in the static generated/ tree, which covers the",
        " * main executable only. They belong to code reached through the overlay",
        " * cache (psxrecomp/docs/COMPILING_OVERLAYS.md).",
        " */",
        "#pragma once",
        "",
    ]
    for b in sorted(bases, key=lambda b: (b["base"], b["name"])):
        lines.append(f"#define PSX_OVL_{b['name'].upper()}_BASE 0x{b['base']:08X}u")
    if bases:
        lines.append("")
    current = None
    for f in funcs:
        if f["overlay"] != current:
            current = f["overlay"]
            lines.append(f"/* ---- {current} ---- */")
        note = f["note"].replace("*/", "* /")
        lines.append(
            f"/* {f['status']}: {note} */" if note else f"/* {f['status']} */"
        )
        lines.append(
            f"#define PSX_FN_{f['overlay'].upper()}_{f['name']} 0x{f['pc']:08X}u"
        )
        lines.append("")
    if not funcs:
        lines.append("/* (no [[func]] entries yet) */")
        lines.append("")
    return "\n".join(lines)


# --- hook drift --------------------------------------------------------------

def game_toml_hooks(path: pathlib.Path) -> set[int] | None:
    if not path.is_file():
        return None
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw = data.get("recompiler", {}).get("mod_function_entry_funcs")
    if raw is None:
        return set()
    return {_parse_int(v) & 0xFFFFFFFF for v in raw}


def check_hooks(funcs: list[dict]) -> int:
    """Verify game.toml's hex list still matches the named map.

    Deliberately reports rather than rewrites: game.toml is hand-authored, and
    silently editing it would make a config change invisible in review.
    """
    want = declared_hooks(funcs)
    have = game_toml_hooks(GAME_TOML_PATH)
    if have is None:
        print(f"error: missing {GAME_TOML_PATH}", file=sys.stderr)
        return 1
    want_pcs = {f["pc"] for f in want}
    if want_pcs == have:
        print(f"ok: game.toml mod_function_entry_funcs matches "
              f"{len(want)} hook=true entr{'y' if len(want) == 1 else 'ies'}")
        return 0

    by_pc = {f["pc"]: f["name"] for f in want}
    for pc in sorted(want_pcs - have):
        print(f"missing from game.toml: 0x{pc:08X}  {by_pc[pc]}", file=sys.stderr)
    for pc in sorted(have - want_pcs):
        print(f"in game.toml but not hook=true in symbols.toml: 0x{pc:08X}",
              file=sys.stderr)
    print("\nPaste into game.toml [recompiler] (regen required to take effect):",
          file=sys.stderr)
    print("mod_function_entry_funcs = [", file=sys.stderr)
    for f in sorted(want, key=lambda f: f["pc"]):
        print(f'    "0x{f["pc"]:08X}",  # {f["name"]}', file=sys.stderr)
    print("]", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if a header would change")
    ap.add_argument("--check-hooks", action="store_true",
                    help="exit 1 if game.toml's hook list drifted from symbols.toml")
    ap.add_argument("--symbols", type=pathlib.Path, default=SYMBOLS_PATH)
    ap.add_argument("--overlay-symbols", type=pathlib.Path, default=OVERLAY_SYMBOLS_PATH)
    ap.add_argument("--header", type=pathlib.Path, default=HEADER_PATH)
    ap.add_argument("--overlay-header", type=pathlib.Path, default=OVERLAY_HEADER_PATH)
    ap.add_argument("--game", default="", help="title label for header comment")
    args = ap.parse_args()

    if not args.symbols.is_file():
        print(f"error: missing {args.symbols}", file=sys.stderr)
        return 1

    game = args.game or game_title(args.symbols)
    funcs = load_funcs(args.symbols)
    ovl_funcs, ovl_bases = load_overlay_funcs(args.overlay_symbols)

    if args.check_hooks:
        return check_hooks(funcs)

    outputs = [(args.header, render_header(funcs, game=game))]
    if ovl_funcs or args.overlay_symbols.is_file():
        outputs.append((args.overlay_header,
                        render_overlay_header(ovl_funcs, ovl_bases, game=game)))

    if args.check:
        stale = [p for p, t in outputs
                 if not p.is_file() or p.read_text(encoding="utf-8") != t]
        for p in stale:
            print(f"out of date: {p}", file=sys.stderr)
        if stale:
            return 1
        for p, _ in outputs:
            print(f"ok: {p}")
        return 0

    for p, t in outputs:
        p.write_text(t, encoding="utf-8")
    print(f"wrote {args.header} ({len(funcs)} funcs)")
    if len(outputs) > 1:
        n_ovl = len({f['overlay'] for f in ovl_funcs})
        print(f"wrote {args.overlay_header} ({len(ovl_funcs)} funcs "
              f"across {n_ovl} overlays)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
