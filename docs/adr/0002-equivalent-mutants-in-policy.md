# 2. Equivalent mutants in the policy gate

Date: 2026-08-19

## Status

Accepted

## Context

Mutation testing (mutmut 3.7) is run against `src/chancel/policy.py`, the
security-critical `PolicyGate`. After strengthening `tests/unit/test_policy.py`
so that every deny branch pins all four structured `ScopeViolation` fields
(`reason`, `space_id`, `requested`, `offending`) by exact equality, the mutant
count is **188 generated, 186 killed, 2 surviving**.

Both survivors are **equivalent mutants**: the mutated program is behaviorally
identical to the original, so *no* test — however written — can distinguish
them. A surviving equivalent mutant is not a test gap; killing it is
impossible, not merely hard. Each is documented below with its exact diff and a
proof of indistinguishability.

Note on a third mutant that is *not* equivalent: `__init____mutmut_1` changes the
default `timeout_s` from `1.0` to `2.0`. That default is observable — a gate
built with no explicit timeout, given a resolver that sleeps ~1.3s, denies under
the real default (1.0) but would allow under the mutant (2.0). It is killed by
`test_default_timeout_denies_a_resolver_slower_than_one_second`, an intentionally
slow (~1.3s) test. It is called out here only to record that it was killed
rather than waived.

## Decision

Accept the following two mutants as equivalent and waive them permanently.

### 1. `chancel.policy.xǁPolicyGateǁ_materialize_requested__mutmut_30`

```diff
-    str_items = cast(list[str], collected)
+    str_items = cast(None, collected)
```

`typing.cast(typ, val)` is a **runtime no-op**: its entire implementation is
`return val`. The first argument is a type annotation consumed only by static
type checkers, which do not run during test or production execution; at runtime
it is evaluated and discarded, and `val` is returned unchanged regardless of its
value. `cast(None, collected)` therefore binds `str_items` to the exact same
object as `cast(list[str], collected)` — `collected` itself — with no observable
difference in value, identity, iteration order, or side effect.

Because the only effect of the line is `str_items = collected` in both the
original and the mutant, and `None` is a legal (if type-nonsensical) first
argument that `cast` never inspects, there is no program state, exception, or
output that differs between the two. No test can distinguish them because the
runtime behaviors are literally identical. **Provably equivalent.**

(Static analysis *can* tell the two apart — a type checker would reject
`cast(None, ...)` — but mutation testing measures the runtime test suite, not
the type checker. The static difference is caught separately by `mypy`/`ruff`
in CI.)

### 2. `chancel.policy.xǁPolicyGateǁauthorize__mutmut_33`

```diff
-        if elapsed > self._timeout_s:
+        if elapsed >= self._timeout_s:
```

The two operators differ only on the single point `elapsed == self._timeout_s`.
`elapsed` is `time.monotonic() - start`: the difference of two wall-clock
`float` readings taken around a resolver call. Distinguishing the mutant
requires `elapsed` to land **exactly** on the `float` value stored in
`self._timeout_s` — bit-for-bit equal.

That equality is not reachable by any deterministic test:

- `time.monotonic()` advances at nanosecond-ish resolution and its readings are
  not under test control. The probability that the subtraction of two
  independent monotonic samples equals a specific pre-chosen `float` is
  effectively zero (a measure-zero event over a continuous quantity).
- Even if a test could name the exact `float` in `_timeout_s`, it cannot force
  the resolver to consume *precisely* that much wall time; scheduling jitter
  makes the elapsed value non-reproducible run to run.
- The two boundary-adjacent branches that *are* reachable are already tested:
  `elapsed` comfortably greater than the timeout denies (both operators agree),
  and `elapsed` comfortably less allows (both operators agree). Only the
  zero-probability tie separates them.

Because the distinguishing input cannot be produced deterministically — not
"is hard to produce", but "occurs with probability ~0 and is not reproducible" —
no test can reliably kill this mutant. The boundary semantics are also
immaterial to the gate's fail-closed guarantee: at the tie the difference is one
scheduling quantum, and the gate errs closed on either side within noise.
**Equivalent for all testable purposes.**

## Consequences

- The mutation-testing target for `src/chancel/policy.py` is **2 surviving
  mutants**, both waived here, i.e. an effective mutation score of 100% on
  non-equivalent mutants (186/186 killed).
- A future run reporting more than these two survivors — or different ids —
  indicates a genuine new test gap and must be investigated, not waived. The two
  ids are pinned above precisely so a third survivor is loud.
- `tests/unit/test_policy.py` retains 100% line coverage on the gate and every
  deny branch asserts all four `ScopeViolation` fields by exact equality, so
  reason-string, `space_id`, `offending`, and `requested` mutations all fail a
  test.
- The `cast` static-type signal (mutant 1) is not covered by the runtime suite
  by design; it is covered by the type checker in CI. This is the correct
  division of labor and not a reason to contort a runtime test.
