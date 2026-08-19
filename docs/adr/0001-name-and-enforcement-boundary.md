# ADR 0001 — The name, and enforcement below the model boundary

**Status:** accepted · **Date:** 2026-08-19

This record covers two decisions taken at the project's start: what the thing is called, and
where its one load-bearing control lives.

## Context

**The name.** The project began as `ringfence` — "ring-fencing" is the term for a regulatory
separation that must hold structurally rather than by policy, which is exactly the claim. A name
gate was run before the first commit, checking availability across the three registries the
project publishes to or is discovered through:

| registry | `ringfence` | `chancel` |
| --- | --- | --- |
| PyPI | 404 — available | 404 — available |
| npm | **TAKEN** — active package, 11 versions, last modified 2026-05-14, *itself a security-isolation tool* (sandboxes npm installs) | 404 — available |
| GitHub | no significant claim | no starred conflict |

`ringfence` on npm is not a dormant squat — it is an active security tool, a direct brand
collision in the same problem space. The PRP defined a fallback chain (`ringfence → chancel →
parclose`), and `chancel` — the screened-off part of a church, separated by a physical screen
through which the service still carries — is if anything the better metaphor: *instructions
travel, client data does not.*

**The enforcement boundary.** The first-version design (`ethical-wall-rag`, v1 of the PRP) leaned
on the Claude Agent SDK's `PreToolUse` hook as the enforcement point. That couples the core
guarantee to one vendor's SDK: change the provider and the wall changes with it, or disappears.

## Decision

**Name.** Package `chancel`, CLI `chancel` with alias `chl`, repo `Nobel-Co/chancel`, environment
prefix `CHANCEL_`. This aligns the identity across PyPI, npm, and GitHub, and eliminates the npm
collision entirely.

**Enforcement.** The wall is `PolicyGate.authorize()`, a provider-neutral function every
retrieval path must pass through. The Agent SDK `PreToolUse` hook is retained as **opt-in defense
in depth for the one adapter that offers it** — never as the wall. The invariant lives in code no
provider can reach.

## Consequences

- The name is collision-free across all three registries and the env prefix matches the project
  name.
- Core isolation is framework-agnostic. Swapping the chat model, embedder, or vector store cannot
  weaken the guarantee, because none of them touches `policy.py`. This is what makes the demo
  matrix's provider columns meaningful: the same wall holds across every adapter.
- The Agent SDK integration is a genuine security bonus for that adapter without becoming a
  dependency of the guarantee. A control that vanishes when you change vendors was never a
  control; this decision moves it somewhere a vendor change cannot reach it. See
  [why.md](../why.md#the-wall-belongs-below-the-provider-boundary).
- Read every `ringfence`/`rf` in the seed PRP as `chancel`/`chl`.
