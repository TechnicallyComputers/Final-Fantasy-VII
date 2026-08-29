# Third-Party Attribution

Framework-level dependencies (OpenBIOS, libchdr, TinyCC, …) are recorded in
`psxrecomp/THIRD_PARTY_ATTRIBUTION.md`. This file covers what *this repository*
takes from elsewhere.

---

## ff7-decomp — function and data names

[ff7-decomp](https://github.com/Xeeynamo/ff7-decomp) — "Matching decomp of Final
Fantasy VII for PlayStation 1" — by **Xeeynamo** and contributors. At the pinned
commit the GitHub contributor list is:

> Xeeynamo, david-martin, halkuncode, Zaarbs, khasinski, KieronJ,
> devcheckra1n, jdperos, AceZephyr, maciej-trebacz, bgullis1, eduardovra,
> MrGuy55, thiago-sinesio, dudhasch, nami1yt

The symbol map in this repository is their work. `symbols.toml` and
`symbols_overlays.toml` would otherwise hold one name.

### Licence status: NONE

**The repository carries no LICENSE file** (the GitHub API reports
`"license": null`). No licence is granted, so their work is all-rights-reserved
and **their source may not be merged here**. `recomp-ai-rules/LICENSING.md` §5
governs this exact case: a decomp is a read-only reference whose useful output
is "symbols and structural understanding", never code.

Recorded before consulting it, per §5.

### What was taken, and what was not

| | |
|---|---|
| **Read** | `config/*.txt` and `config/us.yaml` — address tables of the form `name = 0x800257CC;`, plus overlay load addresses and image hashes |
| **Not read, not merged** | everything under `src/` — the decompiled C |

Addresses are facts, not protected expression (`LICENSING.md` §2), which is what
makes the import legitimate where merging the source would not be.

The restriction is **structural, not a promise**: `tools/import_decomp_symbols.py`
routes every read through a guard that refuses any path outside `config/`. A
future edit cannot widen it by accident.

### The pin

```
repo:    Xeeynamo/ff7-decomp
commit:  24a46a990dccc7dad4cac107408df00b0cac6c4c   (2026-08-27)
licence: none
```

Bump `DECOMP_COMMIT` in the importer deliberately. A moving reference silently
changes names already cited elsewhere.

### Identity gate

§5 requires symbol import to abort when the reference's image hash disagrees
with the project's, enforced by the tool rather than by discipline. The decomp's
`main` overlay and our own boot executable are byte-identical:

```
config/us.yaml  main.sha1 = a95e8b16b97071203b953bb81a33980509262f30
disc/SCUS_941.63          = a95e8b16b97071203b953bb81a33980509262f30
```

So every imported address is directly valid in our address space with no
rebasing. The importer recomputes and compares this on every run and refuses to
write anything on mismatch.

### Provenance tagging

Every imported entry is `status = "contextual"` — evidence-backed but
**unverified by us**. §5: a contextual name must never later be cited as
evidence. Promotion to `confirmed` requires independently observing the
behaviour; the `hook-trace` feature of `mods/preloaded/packages/ff7.enhancements`
exists to do that.

### Independent corroboration

`python3 tools/import_decomp_symbols.py --verify-generated` checks the imported
addresses against the function entries **our own recompiler proved from the
image**, with no input from the decomp:

```
our recompiler proved 1480 function entries in generated/
imported main symbols: 581
  on a proven function entry : 488 (84.0%)   <- boundary corroborated
  g_*-style data names       :  87           (expected not to be functions)
  neither                    :   6
```

Two independent analyses agree on where 488 functions start. That corroborates
**boundaries only** — it says nothing about whether a name is correct, which is
why nothing is promoted out of `contextual` by this check.

The six unmatched are `ChangeClearSIO`, `ReadOTZ`, `ReadLZC`, `DecDCTvlcSize`,
`sprintf` (PSY-Q library functions our static pass never reached — candidates
for `seeds/ghidra_funcs.txt`) and `Savemap` (data, not a function). A hook
placed on any of them would silently never fire.

### If licensing is ever pursued

Two things to know before opening that conversation:

1. **Xeeynamo's other decomp, `sotn-decomp`, is AGPL-3.0.** Under
   `LICENSING.md` §1 that tier is *never vendor, never link*. Asking for "a
   licence" without naming one risks getting the one that forecloses the option
   permanently. Ask for a specific permissive licence (MIT / BSD-3-Clause), or a
   dual licence.
2. **Sixteen contributors hold copyright**, not one. Relicensing needs sign-off
   from all of them.

Nothing in this repository depends on that conversation happening. The symbol
import stands on its own.
