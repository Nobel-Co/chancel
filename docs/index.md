# chancel

**Provable scope isolation for AI retrieval.** Firm-level instructions travel everywhere; a
client matter's data provably never crosses a matter boundary — enforced *below the model
boundary*, so the guarantee survives swapping the AI provider.

The whole argument is one table, the literal output of `chancel demo --no-llm`, run cold-clone
with no API key and no Docker:

```
finding                 backend   provider      expected  actual  ok
----------------------  --------  ------------  --------  ------  --
canary-leak             isolated  echo          clean     clean   ✓
unrepresentable-call    isolated  n/a           denied    denied  ✓
deletion-verifiability  isolated  n/a           clean     clean   ✓
canary-leak             filtered  echo          clean     clean   ✓
unrepresentable-call    filtered  n/a           leaked    leaked  ✓
canary-leak             shared    echo          leaked    leaked  ✓

PASS: 12/12 cells matched their predicted color
```

`isolated` holds; `filtered` (the vendor-default multitenancy pattern) leaks on the findings
collection separation makes impossible; `shared` (prompt-only "isolation") leaks first.
"Green" means every cell behaved as *predicted*, reds included — not that nothing leaked.

## Read next

- **[Why](why.md)** — the piece to read if you read one. Matter isolation as a migration
  argument, the four memory tiers and where the commercial value sits, and why a control that
  disappears when you change vendors was never a control.
- **[Architecture](architecture.md)** — three diagrams (request path, the three backends side by
  side, the memory-promotion gate) and the module-by-module contract.
- **[Threat model](threat-model.md)** — what it defends, what it does not, and the trust
  boundaries.
- **[Adding a provider](adding-a-provider.md)** / **[Adding a store](adding-a-store.md)** — the
  drop-in adapter walkthroughs.
- **Decision records** — [name & enforcement boundary](adr/0001-name-and-enforcement-boundary.md),
  [collection-per-space vs vendor default](adr/0003-collection-per-space-departs-from-vendor-default.md),
  [audit hash chain](adr/0004-audit-hash-chain.md).

`chancel` is a **demonstration, not a product**. It carries zero real data (the corpus is
synthetic and script-generated). Out of scope, named so omission is not mistaken for oversight:
authentication, RBAC, multi-user sessions, key management, retention, egress DLP, answer-quality
evaluation, any UI, any hosted deployment.
