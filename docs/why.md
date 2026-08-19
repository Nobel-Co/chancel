# Why

Most writing about matter isolation frames it as a security control: keep one client's documents
away from another client's context, because leakage is a breach. That is true, and it is the
smaller half of the argument. The larger half is that the isolation guarantee is a **migration
argument** — it is the thing that lets the data show up at all.

## Isolation is the permission slip

A retrieval assistant is only as useful as the corpus it can see. The realistic failure mode for
one inside a firm is not that it leaks — it is that it never gets fed. A partner asked to upload
"the matter file" to an AI tool does not upload the matter file. They upload three documents they
have personally decided are safe, because they cannot reason about what the tool will do with the
rest, and the cost of being wrong is a confidentiality breach they are personally accountable
for. The assistant then answers from a fraction of the record and quietly gives worse answers
than a junior with access to the drawer.

What changes that calculation is not a better model. It is a guarantee the partner can restate in
one sentence and defend under questioning: *this matter's documents are in their own physical
store, and no query from any other matter can reach them, because there is no way to phrase such
a query.* When the guarantee is structural — when a cross-matter read has no signature that can
express it, rather than a policy that promises not to — the permission slip gets signed and the
whole matter file gets uploaded instead of three documents. Isolation is what unlocks the corpus.
Security is the mechanism; the migration is the payoff. A tool that cannot make the promise stays
starved no matter how good its retrieval is.

This is why `chancel` spends its effort on making the wrong thing *unrepresentable* rather than on
detecting it. A detector is a promise with a track record; unrepresentability is a fact about the
type system and the storage layout. The partner can be told the difference, and it is the
difference that moves the data.

## The four moving parts of memory

Retrieval is only half of what an assistant remembers. The other half is what it *learns* — the
distilled facts, playbooks, and house style it carries forward. `chancel` models that with three
tiers and one gate between them: four moving parts.

- **Personal** memory crosses matters but belongs to one user: their own notes and shorthand. It
  is already the widest tier a single person sees, so nothing is ever promoted *into* it.
- **Matter** memory never leaves its space. A fact learned inside one matter lives and dies
  there. This is the retrieval wall's analogue on the learning side.
- **Firm** memory crosses every matter: the playbooks, the drafting conventions, the "how this
  firm handles an indemnity clause" that every engagement should benefit from.
- **The promotion gate** is the fourth part, and the load-bearing one. A fact may be promoted
  from matter to firm tier *only if every provenance ID it cites belongs to the firm corpus.* One
  space-scoped source, and the whole promotion is refused, by name. There is no "promote anyway"
  flag — exactly as there is no collection parameter on the retriever.

The firm tier is the one with commercial value, and the gate is what makes that value bankable. A
firm's accumulated judgment — its playbooks, its house positions, the institutional knowledge
that outlasts any individual — is an asset that compounds. But it only compounds if it is clean:
the moment a matter-specific fact is laundered into firm memory, the institutional tier stops
being shareable, because it now silently carries one client's confidential data into every other
client's context. The personal and matter tiers are private by construction and carry no
cross-matter risk. The firm tier is the only one worth building deliberately *and* the only one a
leak can poison. The promotion gate exists so the valuable tier can be trusted — so an
institution can invest in it without the investment becoming a liability.

## The wall belongs below the provider boundary

There is a tempting place to put the isolation control: in the AI vendor's own tooling — a
system prompt the model is told to obey, a hook the vendor's SDK offers, a filter their client
library applies. It is tempting because it is where the retrieval appears to happen.

It is the wrong place, for a reason that has nothing to do with any particular vendor: **a control
that disappears when you change vendors was never a control.** If the guarantee lives in the
prompt, it evaporates the day the model decides not to follow it — and the whole point of the
`shared` backend in this repo is to show that day is trivial to reach. If it lives in the vendor's
SDK, it evaporates the day you swap the vendor, and it protects exactly one integration in the
meantime. Either way the partner's one-sentence promise now has an asterisk pointing at a third
party's roadmap, and an asterisk is not something you defend under questioning.

So the wall lives in `PolicyGate.authorize()`, a provider-neutral function every retrieval path
must pass through. No provider touches it; swapping the model, the embedder, or the vector store
cannot weaken it, because none of them can reach it. The vendor's own hook remains available as
*defense in depth* for the one integration that offers it — but it is a second lock on a door
that is already load-bearing, not the door. The guarantee is the same whether the model is
hostile, broken, or absent, because the enforcement runs whether or not the model reads the
prompt, honors it, or exists at all.

That is the whole design in one line: instructions travel, matter data does not, and the thing
enforcing it does not care who is answering the question.
