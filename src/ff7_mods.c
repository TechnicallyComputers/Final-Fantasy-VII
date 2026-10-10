/* ff7_mods.c — developer hook tracing for Final Fantasy VII.
 *
 * The retired widescreen activation now lives in the replacement enhanced
 * renderer package, implemented by src/ff7_renderer.c.
 *
 * See psxrecomp/docs/MOD_PACKAGES.md ("Trusted static plugins") and
 * runtime/include/mod_plugins.h.
 */

#include "mod_plugins.h"

/* Generated from symbols.toml by tools/sync_symbols.py. Quote-include by
 * relative path on purpose: runtime.cmake deliberately keeps the repo root
 * off -I so a case-insensitive filesystem cannot resolve #include <version>
 * to the VERSION pin file. */
#include "../psx_symbols.h"

#include <stdio.h>
#include <string.h>

/* Must match mods/preloaded/packages/ff7.enhancements/<version>/manifest.toml.
 * psx_mod_option_value() resolves by id because registration is by plugin id
 * alone and the callback carries no package/feature context. */
#define FF7_MOD_PACKAGE "ff7.enhancements"

/* ---------------------------------------------------------------------------
 * Hook trace — the instrument that turns a "contextual" name into a confirmed
 * one.
 *
 * symbols.toml carries ~580 function names imported from the ff7-decomp symbol
 * map. Per recomp-ai-rules/LICENSING.md §5 those are tagged status =
 * "contextual": evidence-backed, but UNVERIFIED BY US, and a contextual name
 * must never be cited as evidence. This feature is how you discharge that —
 * enable it, do the thing the name claims to describe, and see whether the call
 * actually fires.
 *
 * It is READ-ONLY. It calls no psx_mod_write_*, changes no guest state, and
 * alters no timing beyond the host-side printf. Nothing here breaks
 * faithfulness, so it needs no ENHANCEMENTS.md policy decision.
 *
 * The hook set is not written out here. It is generated into psx_symbols.h from
 * every symbols.toml entry with hook = true, so adding a hook is a one-line
 * edit to the map — never a hex address typed into C
 * (psxrecomp/docs/SYMBOLS.md: "Do not leave newly identified functions as raw
 * hex in host hooks").
 *
 * The call sites themselves are emitted by the recompiler from game.toml
 * [recompiler] mod_function_entry_funcs, so a change to the hook set only takes
 * effect after generated/ is rebuilt. `tools/sync_symbols.py --check-hooks`
 * fails when those two drift apart.
 * ------------------------------------------------------------------------- */

#define FF7_MOD_HOOKTRACE_FEATURE "hook-trace"

/* Per-function cap. A hook on a per-frame function would otherwise drown the
 * console and change the very timing you are trying to observe. */
enum { FF7_TRACE_LIMIT = 8 };

static int s_trace_active;

static struct {
    uint32_t address;
    const char* name;
    unsigned long count;
} s_trace_hooks[] = {
#define FF7_TRACE_ROW(name, addr) { (addr), #name, 0UL },
    PSX_FN_HOOK_LIST(FF7_TRACE_ROW)
#undef FF7_TRACE_ROW
};

enum { FF7_TRACE_HOOK_COUNT =
           (int)(sizeof(s_trace_hooks) / sizeof(s_trace_hooks[0])) };

/* If these disagree, psx_symbols.h was regenerated without rebuilding this
 * translation unit, and the table below no longer describes the emitted hooks. */
typedef char ff7_trace_hook_count_matches_header[
    (FF7_TRACE_HOOK_COUNT == PSX_FN_HOOK_COUNT) ? 1 : -1];

static void ff7_hook_trace_activate(void) {
    s_trace_active = 1;
    printf("[ff7.hook-trace] armed; %d hook(s), first %d entr%s each:\n",
           FF7_TRACE_HOOK_COUNT, (int)FF7_TRACE_LIMIT,
           FF7_TRACE_LIMIT == 1 ? "y" : "ies");
    for (int i = 0; i < FF7_TRACE_HOOK_COUNT; ++i) {
        printf("[ff7.hook-trace]   0x%08X  %s\n",
               s_trace_hooks[i].address, s_trace_hooks[i].name);
    }
    fflush(stdout);
}

static void ff7_hook_trace_entry(struct CPUState* cpu, uint32_t address) {
    (void)cpu;
    if (!s_trace_active) return;

    for (int i = 0; i < FF7_TRACE_HOOK_COUNT; ++i) {
        if (s_trace_hooks[i].address != address) continue;
        const unsigned long n = ++s_trace_hooks[i].count;
        if (n <= (unsigned long)FF7_TRACE_LIMIT) {
            printf("[ff7.hook-trace] %s (0x%08X) entry #%lu\n",
                   s_trace_hooks[i].name, address, n);
            if (n == (unsigned long)FF7_TRACE_LIMIT) {
                printf("[ff7.hook-trace] %s reached the cap; "
                       "further entries suppressed\n", s_trace_hooks[i].name);
            }
            fflush(stdout);
        }
        return;
    }

    /* No row for an address the recompiler emitted a hook at. That is a real
     * inconsistency between game.toml's list and this build's psx_symbols.h,
     * not a benign case — trap loudly rather than dropping it silently. */
    printf("[ff7.hook-trace] UNKNOWN HOOK ADDRESS 0x%08X — game.toml "
           "mod_function_entry_funcs and symbols.toml hook=true disagree; "
           "run tools/sync_symbols.py --check-hooks\n", address);
    fflush(stdout);
}

PSX_MOD_CONSTRUCTOR(register_ff7_mods) {
    (void)psx_mod_register_activation_plugin("ff7.hook-trace",
                                             ff7_hook_trace_activate);
    /* One callback serves every hook; it dispatches on the address the runtime
     * passes back. Registration is per (id, address). */
    for (int i = 0; i < FF7_TRACE_HOOK_COUNT; ++i) {
        (void)psx_mod_register_function_entry_plugin(
            "ff7.hook-trace", s_trace_hooks[i].address, ff7_hook_trace_entry);
    }
}
