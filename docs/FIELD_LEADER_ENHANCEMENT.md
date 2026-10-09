# Optional added character field leader enhancement

**Deferred beyond first release.** Sephiroth's independent battle party,
PHS, equipment, materia and saves do not require him to lead exploration.
First release retains the original story-selected field and world-map avatars.
The field-control prototype remains uncommitted and is not ready for ordinary
play. Implementation and live testing are paused.

## Native control and the observed failure

Battle party order at `0x8009CBDC` and stored field order at `0x8009D391` are
distinct. The native membership merge at `0x800CF60C` preserves surviving field
members' order. Moving Sephiroth to the first battle slot alone therefore keeps
the previous field leader. Changing normal PHS/story permissions is separate
from selecting the field actor.

In an explicitly authored diagnostic save, both banks placed the independent
Sephiroth first. Field initialization bound him to entity 12/model 10, placed
his own model and rendered it. Input still moved an invisible native actor.
The cause was the original MD1STIN director's `BF 01` command at script offset
`0x4A1` (`0x4E9` in the expanded script). Opcode BF selects the controllable
script entity. After the added actor's initialization, this command selected
Cloud entity 1/model 0 again. Cloud's script had hidden that actor because
the stored field leader was Sephiroth.

The original BF handler is `0x800C5668..0x800C573C`. It uses the entity-to-model
table at `0x8007EB98` and writes the control context's model byte at offset
`0x2A`. The live context was `0x8009ABF4`, with the byte at `0x8009AC1E`.
The director cursor at `0x4EB` established that the original BF command had run.

## Proposed profile selected adapter

The prototype adds `field_control_policy` to immutable `FF7PartyProfile`:

- `FF7_PARTY_FIELD_CONTROL_NATIVE = 0` preserves original selection.
- `FF7_PARTY_FIELD_CONTROL_PARTY_AVATAR = 1` opts an added profile into routing
  control of an active native party actor to its own field avatar.

This is runtime policy, not a new saved identity or envelope version. The
uncommitted Sephiroth descriptor currently opts in; first-release integration
must exclude that prototype or retain policy zero.

The single added instruction seam is `0x800C56C8`, expected word `0x24A531FC`,
with an exact 13-word surrounding guard. It runs after the BF entity operand
load and changes only `a0`/GPR 4 before the original handler resolves the model.

Routing requires all of the following:

1. The stored leader is an active registered extra with the explicit policy.
2. The requested entity belongs to an active native character ID 0-8.
3. The extra owns a valid bound field entity and model.
4. Its model is distinct from all other native and added-character bindings.
5. The instruction context matches the owned original code.

Native leaders, NPCs, reserve actors, flashback aliases 9/10, unknown policies,
unbound entities and invalid/shared models retain the original operand. The
adapter allocates no memory and does not rewrite scripts, poses, native entity
maps, CPU PC or script cursors. The original BF handler performs the control
assignment and cursor advancement.

The policy can still override a scene's deliberate selection of another active
native party member. That is a real story/cutscene compatibility concern even
with the NPC and binding guards. Camera, followers and scene scheduling require
their own acceptance before enabling the enhancement.

## Existing evidence and its limits

- Strict field/loader fixtures and compilation against production headers pass.
- Across all three owned discs, 96 complete original BF fixture calls and 78
  owned MD1STIN BF/frame calls pass for guest proxies 11 and 26. These checks
  preserve scripts, native maps and independent pose storage.
- A live diagnostic changed the ignored cloned BF operand from entity 1 to 12
  and reran the original handler. It selected model 10; directional input moved
  Sephiroth's coordinates while hidden native model 0 remained stationary.
  This established the control cause and feasibility.
- That diagnostic script edit is not the production callback. The new guarded
  callback has not passed a full Release build and live gameplay acceptance.

Prototype sources are `src/ff7_party_field.c`,
`src/ff7_party_field_sites.inc`, and the profile declarations/descriptor in
`src/ff7_party_game.h` and `src/ff7_party_game.c`. Guards and fixture results are
in `mods/preloaded/packages/ff7.expanded-party/field-hooks.evidence.json` and
`field-hooks.validation.json`; owned loader checks are recorded separately in
`field-loader.validation.json`. These working-tree reports describe a future
prototype, not a shipped capability.

## Work required if the enhancement is resumed

Keep this work separate from the first-release party integration. Reconcile
the prototype and its single configured hook, build the intended configuration,
then test live avatar movement, camera/followers, battle return and map reload.
Include native-leader, NPC and scene-selected active-party controls to check
that opting in does not break important story behavior.

World-map leadership is a separate asset/control feature; this field callback
does not supply new world-map models. Broader scene participation or new
Sephiroth dialogue is also separate scope. Additional profiles must explicitly
opt into the policy after their own entity/model bindings are validated.

First-release acceptance remains in [the burndown](RELEASE_BURNDOWN.md).
