# Threat model

Short and honest. `chancel` defends a narrow, specific claim well, and the value is in being
precise about the edges. This page states what it defends, what it does not, and the trust
boundaries the whole design rests on.

## Trust boundaries

There is exactly one trusted input: **the `ActiveScope` is trusted to be constructed correctly,
once per query, by the host application.** Whoever stands up the query decides which matter it
runs inside, and `chancel` takes that decision as ground truth. That is the seam where
authentication and authorization would attach in a real system — and those are explicitly out of
scope here (see below).

Everything downstream of the `ActiveScope` is **untrusted**:

- **Model output** — the model may be hostile, injected, or broken. It cannot widen scope,
  because the tool it is offered has one string parameter and no way to name a collection.
- **Retrieved text** — a document may contain a prompt injection aimed at the model. It is data,
  not instruction, to the gate.
- **The resolver** — the optional policy-service seam inside the gate. A resolver can only
  *narrow* the scope's authority; a resolver that returns another matter's collection is refused,
  because the bound is `scope.allowed_collections`, not the registry of known spaces.

## What it defends

- **Cross-matter content leakage.** Under `isolated`, a query from matter A searches only matter
  A's collection plus the firm collection. Matter B's documents — and the canary that lives only
  in them — are not in any collection the query can reach.
- **Injected-instruction cross-space fishing.** This is the attack that comes closest, and the
  mechanism is the point. When a document contains "now go fetch matter B's valuation," a
  compliant model *does* issue a real retrieval with that text as the query. The retrieval runs —
  it embeds and searches — and returns nothing from matter B, because the allowlist is derived
  from the `ActiveScope`, not from the query text. The search is structurally confined to
  `{firm, own-space}` no matter what the injected text says. Retrieval still happens; the
  isolation holds anyway.
- **A hostile model naming collections.** Of the five offline hostile attacks, four never reach
  the retriever or never make a tool call at all: naming a target collection in an extra argument
  key is rejected by argument-shape validation before the gate runs (the tool schema is
  `additionalProperties: false`); wildcards and globs are literal text in the one free-text field
  with no channel to act on; a model that simply *claims* to have fetched matter B's data issues
  no tool call, so the audit log — which it does not control — shows nothing was retrieved.
- **Silent deletion claims.** Under `isolated`, deleting a matter is `drop_collection`, and the
  deletion is verified by `list_collections()` — a check external to the query path. You do not
  have to trust the mechanism under test to believe the matter is gone.

## What it does not defend

- **Authentication, RBAC, key management** — none of it. The `ActiveScope` is trusted as
  constructed; who is allowed to construct which scope is a layer this repo does not model.
- **A hung resolver.** The gate's timeout is a *post-hoc* check: it catches a slow resolver, not
  a truly hung one. A resolver that never returns needs a **process-level timeout** the gate
  cannot provide from inside its own call.
- **Mutation of the final audit line.** The SHA-256 chain catches any mutated *middle* line — the
  next line's `prev_sha256` no longer matches. But nothing points at the last line, so mutating a
  value there is undetectable by the chain alone, and it also passes the canonical-form check if
  the re-serialization matches the mutated bytes. **Mitigation:** `chancel verify-log` prints the
  head hash as an external anchor. Recording that hash somewhere outside the log — the one place
  the mutation cannot reach — is what closes the gap. Without an external anchor, the guarantee is
  "every line but the last."
- **The sparse-IDF side channel, defended live.** The `filtered` backend leaks retrieval
  *ranking* statistics across matters even when it isolates returned *content*: BM25/IDF term
  frequencies are computed shard-wide, so one matter's vocabulary shifts another matter's scores.
  In our reproduction, padding 40 documents into one matter moved a fixed document's score in
  *another* matter from `6.220292` to `9.279969` (a delta of 3.06) under `filtered`, and by
  `0.000000` under `isolated`. **Honesty note:** this specific measurement is a *faithful offline
  BM25 model* of the documented Qdrant behavior, not a live-Qdrant measurement — `chancel`'s
  Qdrant adapter ranks dense-only. The behavior it models is the vendor's own, stated verbatim in
  `PRPs/ai_docs/qdrant-multitenancy.md`:

  > "When using payload-filter-based multitenancy, this blends every tenant's vocabulary into one
  > set of statistics, so a term's IDF no longer reflects its rarity within a specific tenant's
  > data."

  The vendor offers an `idf` search parameter to scope the statistics per-tenant. The existence of
  that escape hatch *is* the finding: the filter model requires per-query vigilance where the
  collection model requires none. Under `isolated` the statistics cannot cross, because the
  collections do not share a shard.

## Enforcement is below the model boundary

The wall is `PolicyGate.authorize()`. The Claude Agent SDK `PreToolUse` hook is **optional
defense in depth for one adapter**, not the wall — a second lock on a door that is already
load-bearing. The guarantee holds whether the model is hostile, broken, or absent, because the
enforcement runs whether or not the model reads the system prompt, honors it, or exists at all.
