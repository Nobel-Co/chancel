# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-08-19

First public release. A demonstration, not a product — see the README's
out-of-scope list.

### Added
- `PolicyGate.authorize()` — the provider-neutral wall every retrieval passes
  through; fails closed on unknown scope, malformed input, resolver failure,
  timeout, empty allowlist, and any resolver attempt to widen authority beyond
  the active scope. 100% statement coverage; mutation-tested to two documented
  equivalent survivors.
- Domain model (`Scope`, `DocumentId`, `ActiveScope`, `RetrievalReceipt`) whose
  types make a cross-space read unrepresentable under the isolated layout.
- Three store layouts behind one interface: `isolated` (the claim), `filtered`
  (the vendor-default payload filter), and `shared` (prompt-only), with an
  `inmemory` reference implementation and a `qdrant` local-mode adapter.
- Provider adapters `anthropic`, `openai_compat`, `echo`, and the offline
  adversarial `hostile_echo`; embedders `hash_stub`, `fastembed_local`, and
  `openai_compat`. Nothing above the adapter boundary names a provider.
- `Retriever` — the sole caller of a store's search, exposing no collection or
  filter parameter — and a neutral `ScopedAgent` loop whose one retrieval tool
  takes a query string only.
- Append-only audit log with a SHA-256 hash chain; `chancel verify-log` names
  the first divergent line and prints the head hash as an external anchor.
- Three-tier memory with `promote_fact()`, which refuses any fact whose
  provenance includes a space-scoped id.
- The leak suite: seven findings asserting the predicted color per backend, and
  `chancel demo` rendering the backend × provider matrix with no API key, no
  Docker, and no model download.
- CLI: `demo`, `ask`, `attack`, `verify-log`, `gen-corpus`.

[Unreleased]: https://github.com/Nobel-Co/chancel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Nobel-Co/chancel/releases/tag/v0.1.0
