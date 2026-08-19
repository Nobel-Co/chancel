# Decisions

## 2026-08-19

### Name gate

**Context:** PyPI `ringfence` 404 (available), but npm `ringfence` TAKEN — active package with 11 versions, last modified 2026-05-14, itself a security-isolation tool (sandboxes npm installs), so a direct brand collision. GitHub had no significant claim. Fallback per PRP: `chancel` — PyPI 404, npm 404, no starred GitHub conflict.

**Decision:** Package `chancel`, CLI `chancel` alias `chl`, repo Nobel-Co/chancel, env prefix CHANCEL_.

**Consequence:** Eliminates collision risk; aligns naming across PyPI, npm, and GitHub; env prefix matches project name.

### Enforcement moved below the model boundary (v1→v2 of the PRP)

**Context:** PolicyGate is the wall; the Claude Agent SDK PreToolUse hook is optional defense in depth for one adapter.

**Decision:** PolicyGate carries the invariant; adapter hooks are opt-in.

**Consequence:** Core isolation is framework-agnostic; Agent SDK integration gains without coupling.

### Collection-per-space departs from the vendor's scaling recommendation

**Context:** The vendor's own docs name strict compliance isolation as the exception.

**Decision:** This repo implements collection-per-space deliberately.

**Consequence:** README must state this design choice explicitly.

### Branch protection gotcha: GitHub Free orgs

**Context:** GitHub Free orgs silently drop protection on private repos.

**Decision:** This repo must remain public for protection to hold; if ever made private, re-verify, do not assume.

**Consequence:** If visibility changes, branch rules must be re-checked before merging main.

### Pinned toolchain resolved 2026-08-19

**Context:** Reproducible builds require exact versions.

**Decision:** All versions pinned; see pyproject.toml for the exact pin list: pydantic 2.13.4, typer 0.27.1, httpx 0.28.1, plus test/dev tools (mutmut 3.7.0, mypy 2.3.1 are current majors).

**Consequence:** Maintenance burden is on dependency review; automation cannot drift.

### Agent-tier ladder in effect

**Context:** Cost/quality tradeoff on design-critical decisions.

**Decision:** Haiku for mechanical phases, Sonnet for design-critical ones; escalations logged here.

**Consequence:** This file becomes the record of which decisions were escalated and why.

## 2026-08-19 — PolicyGate review finding (pre-merge)

**Context.** First implementation of `PolicyGate.authorize()` bounded the resolver's
allowlist by the gate's universe (firm + every known space). A hostile or buggy resolver
returning another known space's collection was inside that bound, so a request naming the
other space's collection would have been granted — a cross-space read through the wall.
Caught in orchestrator review of the implementing agent's own deviation notes, before merge.

**Decision.** The resolver bound is `scope.allowed_collections`, not the gate's universe. A
resolver can only narrow the scope's structural authority; widening is unrepresentable
regardless of what it returns. Regression test: `test_resolver_cannot_widen_to_another_known_space`.

**Consequence.** The gate's authority derives from the ActiveScope alone. No escalation of
agent tier was needed — the finding was a spec defect, not an implementation failure.

## 2026-08-19 — Build execution notes (agent-tier ladder and findings)

**Agent-tier ladder as run.** Every phase ran at its PRP-assigned floor and passed
validation, so no failure-driven tier escalation occurred. Haiku carried Phase 0 doc
caching, Phase 1 scaffold, Phase 6 audit log, and Phase 9 CI; Sonnet carried the
security-critical and reasoning-heavy phases (gate, stores, adapters, hostile model,
conformance, leak suite, mutation hardening, docs, simplify). Two items were resolved by
the orchestrator directly rather than by escalating an agent:
- The Qdrant per-tenant IDF documentation and the PyPI trusted-publishing pages were behind
  Cloudflare for the Haiku doc agents; the orchestrator fetched them (a real browser for
  PyPI) and appended the verbatim citations. This is the load-bearing quote for leak finding 2.
- A cross-space hole in the first PolicyGate draft (resolver allowlist bounded by the gate's
  universe rather than the active scope) was caught in review and sent back for a fix plus a
  regression test. See the PolicyGate review-finding entry above.

**Mutation testing.** mutmut 3.7 renamed its config keys; `source_paths`/`only_mutate`/
`also_copy` are required, and the whole package must be copied into the sandbox for the
mutated module's imports to resolve. First pass left 40 survivors — all genuine assertion
gaps (loose reason-substring matches, unasserted exception fields, an unexercised `?` in a
collection name). Hardened tests/unit/test_policy.py to pin all four ScopeViolation fields on
every deny branch; two provably-equivalent mutants remain, justified in ADR 0002 and enforced
by an exact-match allow-list (tests/mutmut_allowlist.txt) in CI.

**Two CI findings after the first GitHub run.** (1) The base-install test tier applied the
whole-package 90% coverage gate, which is unmeetable without the optional adapters installed
(78% observed); the gate now lives only on the extras tier (PR #5). (2) Branch protection was
first configured with the lowercase job *keys* as required status-check contexts, but GitHub
matches on the check-run *names*; the phantom contexts blocked every merge until corrected to
the display names.

**Release handoff.** The v0.1.0 tag is deliberately NOT pushed. PyPI Trusted Publishing
requires a pending publisher configured on pypi.org (owner Nobel-Co, repo chancel, workflow
release.yml, environment pypi) — a browser step only the account owner can perform. Pushing
the tag before that step would fail the pypi-publish job. Configure the publisher first, then
`git tag v0.1.0 && git push origin v0.1.0` triggers build, PyPI publish, and the GitHub Release.
