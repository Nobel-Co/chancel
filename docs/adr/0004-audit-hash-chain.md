# ADR 0004 — Audit log as an append-only SHA-256 hash chain

**Status:** accepted · **Date:** 2026-08-19

## Context

Every retrieval decision — allow or deny — needs to be recorded so a claim about what the system
did is checkable against something the model does not control. Two properties matter: the record
must be **append-only in practice** (tampering with history should be detectable, not just
discouraged), and a receipt must **never carry the query text** (the log is an audit artifact,
not a second copy of the confidential question).

## Decision

The audit log is **append-only JSONL with a SHA-256 hash chain**. Each receipt is serialized in a
canonical form (sorted keys, no whitespace variance), and each line carries a `prev_sha256` field
holding the SHA-256 of the previous line's bytes. The first line's `prev_sha256` is 64 zeros.
Receipts carry only a SHA-256 *fingerprint* of the query, never the query itself.

`verify_log` walks the file and checks, per line: valid receipt, chain linkage, scope consistency
(no receipt names a collection outside its own scope), and canonical form. It returns the first
bad line by number.

## Consequences

- A value mutation in any **middle** line is caught: the following line's `prev_sha256` no longer
  matches the mutated bytes, and `verify_log` names the break.
- A mutation of the **final** line is *not* caught by the chain alone — nothing points at the last
  line — and it also survives the canonical-form check if the mutated value re-serializes to the
  mutated bytes. This is a real, documented limitation, not an oversight.
- **Mitigation:** `chancel verify-log` prints the log's head hash. Recording that hash in a
  location outside the log — the one place a tamperer editing the log cannot reach — turns it into
  an external anchor that pins the final line too. Without such an anchor, the honest statement of
  the guarantee is "every line but the last." See
  [threat-model.md](../threat-model.md#what-it-does-not-defend).
- The log is safe to retain and share for audit purposes, because it never contains query
  content — only fingerprints, decisions, and the collections each decision touched.
