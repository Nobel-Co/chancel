# ADR 0003 — Collection-per-space departs from the vendor default

**Status:** accepted · **Date:** 2026-08-19

## Context

The vector-store vendor's own multitenancy guidance recommends *against* the layout `chancel`'s
defended backend uses. Its words, verbatim:

> "Creating a separate collection for each tenant is rarely the most efficient approach. Each
> collection carries its own resource overhead, so creating many collections can quickly become
> expensive. Only create multiple collections when you have a limited number of tenants that need
> strict isolation."

Taken at face value, that reads as an argument for the `filtered` backend — a single shared
collection with a payload filter per tenant — and against `isolated`. A reader who stops at the
first sentence would conclude `chancel` is doing the wrong thing on purpose.

## Decision

`chancel` implements **collection-per-space** as its defended backend, deliberately departing from
the vendor's default. The departure rests on two distinctions.

**Scaling versus security.** The recommendation is a *scaling* recommendation. Its stated cost is
*resource overhead* — collections are expensive, clusters cap at ~1000 of them, and thousands of
small similar tenants should share one. None of that is a security claim; it is an efficiency
claim, and it is correct on its own terms.

**The vendor's own named exception.** The same sentence names the exception explicitly: *"a
limited number of tenants that need strict isolation."* A law firm's matters are exactly that — a
bounded set of tenants where the isolation requirement is regulatory, and where the isolation
benefit plainly outweighs the operational cost of extra collections. `chancel` occupies the
exception the vendor itself carved out, not a blind spot.

## Consequences

- The README and docs must state this reasoning wherever the layout choice appears, so the
  departure never reads as ignorance of the vendor guidance. It reads as taking the guidance
  *including its exception clause*.
- The choice buys structural unrepresentability: under `isolated` a cross-matter read has no
  signature to express it, deletion is `drop_collection` verified externally, and the ranking
  statistics of one matter cannot touch another's.

**The sparse-IDF side channel is the evidence.** The `filtered` model does not merely risk a
forgotten filter — it leaks in a way collection separation structurally cannot. BM25/IDF ranking
statistics are computed shard-wide, so one matter's vocabulary shifts another matter's relevance
scores even when returned content is correctly filtered. In our reproduction, padding 40
documents into one matter moved a fixed document's score in *another* matter from `6.220292` to
`9.279969` under `filtered`, and by `0.000000` under `isolated`. (This is a faithful offline BM25
model of the documented Qdrant behavior, not a live-Qdrant measurement — see
[threat-model.md](../threat-model.md).) The vendor documents the behavior and offers an `idf`
search parameter to scope statistics per tenant. That escape hatch is the whole point: the filter
model requires per-query vigilance the collection model never asks for. Under separate
collections the statistics cannot cross, because the collections do not share a shard.
