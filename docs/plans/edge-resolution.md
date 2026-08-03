# Plan: type-aware edge resolution

**Status:** Landed behind the `resolution` extra. Spike findings and measurements below.
**Scope:** Atlas fidelity. No new detector, no new product surface, no change to what a
verdict is allowed to rest on.

## The problem

Every detector reads the atlas's edges, and the atlas's edges come from one static AST
parse. That parse cannot see an implementation registered through a factory, wired by a
dependency-injection container, bound by a decorator — or, the case this repository ships
as its own hardest example, an adapter that conforms to a `Protocol` structurally without
ever naming it. `eval/cases/audiobook-studio` documents the consequence: its adapters
"conform structurally rather than inheriting", so a detector that reads a port by the
spelling of its base class finds nothing there and reports a clean bill of health.

This makes the sole-implementation detector confidently wrong in a specific, checkable
direction: it says *exactly one implementation* to the engineer who wrote the second one.
The roadmap (README, "Ranked for adoption") already ranks this above any new detector,
and the ranking is the point of this plan: a fourth detector would be blind in the same
way as the three that exist, while resolving edges better lifts all three at once. Depth
before breadth.

## The rule that survives unchanged

A type checker may inform **detection**, never a **verdict**, and nothing it emits —
diagnostics, rule names, error codes — ever reaches the model. It is an edge oracle:
"this call lands there", "this class satisfies that protocol". The candidate's stated
limitations shrink; the division of labour does not move.

## Candidate backends

The depth has to come from an existing tool — inference is a solved problem that this
project must not re-solve badly.

| Backend | How it would be asked | For | Against |
| --- | --- | --- | --- |
| **mypy (as a library)** | `mypy.build` with `export_types`, plus its internal subtype machinery for `Protocol` conformance | Pure-Python dependency; programmatic access to inferred types; structural subtyping is a first-class question it can answer | Internal APIs are not stability-guaranteed; a version pin is load-bearing |
| **pyright (LSP)** | definition/hover requests per unresolved reference | The most accurate inference available | Ships on node; driving an LSP server from a pip-installed tool is a process boundary and a packaging burden |
| **jedi** | `Script.infer` per reference | Lightest; trivially embedded | Weakest exactly where it matters — protocol conformance — and conformance is the crux |

Working assumption: **spike mypy first**, hold pyright in reserve if mypy's resolution
rate disappoints. Jedi is the fallback only if both prove too heavy, accepting that it
solves the call-edge half and not the conformance half.

## Spike findings (2026-08-02, mypy 2.3.0)

The spike ran both questions against `eval/cases/audiobook-studio/repository` from a
throwaway environment, touching nothing in this repo. Verdict: **go on mypy; do not
spike pyright.** It answered both questions correctly on the example in under half a
second, and the one place it disagreed with the fixture turned out to be a fact about
the fixture, not a backend weakness — pyright would say the same thing, from behind a
process boundary.

What the spike established, in order of consequence:

1. **Strict subtyping rejects the headline example — correctly.** `QwenSynthesis`
   narrows `narrate`'s parameter (`voice: QwenVoice | QwenBuiltinVoice` where the
   protocol says `voice: Voice`), which is contravariance-unsafe; `mypy.subtypes.is_subtype`
   says no, and the mypy CLI flags the same thing inside the fixture itself. A strict
   oracle would therefore never emit the `IMPLEMENTS` edge the acceptance test needs.
   The fix is a policy, not a backend swap: a **relaxed conformance rule** — every
   protocol member present, return types checked with `is_subtype`, parameters checked
   by arity only — scores 8/8 on the spike's positive and negative pairs, still built
   from mypy's own primitives, and credits the ordinary adapter idiom of narrowing a
   parameter. Edge provenance records which rule fired: `conformance: strict | structural`.
2. **Zero-member protocols must be skipped outright.** `Voice` has no members, so
   *everything* satisfies it — `int <: Voice` is true. A naive class × protocol sweep
   would wire every class in the repo to `Voice`. (`runtime_checkable` is irrelevant;
   mypy ignores it for static subtyping.)
3. **The two capabilities compose; neither alone closes the loop.** Calls through the
   registry resolve to the *protocol* method (`main.py`'s `narrate` →
   `SynthesisProvider.narrate`), never to `QwenSynthesis.narrate` — the registry erases
   the concrete type, and no type checker can recover it. Concretely-typed call sites
   (the tests) do resolve to implementations. So call edges join callers to the port,
   and `IMPLEMENTS` edges join the port to its implementations; the sole-implementation
   detector needs the pair.
4. **mypy's incremental cache is useless here** — a fully-warm run exports zero types
   and loads zero trees. Run with `incremental=False` every time and lean on the
   existing content-fingerprint cache. Cost: 0.4s on audiobook-studio; ~9s on this
   repository's 74 files when third-party dependencies are followed (the dependencies
   are the cost, not the repo).
5. **API fragility is real but bounded.** The wheel is mypyc-compiled, so
   `TraverserVisitor` cannot be subclassed — expression walking is a small hand-rolled
   reflective walk instead. `find_member` is the churn-prone internal; `is_subtype` is
   the stable one. `BuildSource` entries need explicit dotted module names, and
   `preserve_asts=True` is required alongside `export_types=True`. All absorbed inside
   the one adapter; the version pin carries the risk.

## Shape of the integration

1. **A port, one method wide.** `EdgeResolver` in `ports/`, asked two questions:
   resolve this reference (path, position) to a definition; does this class satisfy this
   protocol. The mypy adapter lives in `adapters/analysis/` beside the AST analyzer,
   and is the only module that imports mypy.
2. **An enrichment pass, not a second parser.** The AST parse runs exactly as today and
   remains the source of nodes. The resolver then upgrades edges: unresolved calls and
   references get targets where the backend can name one, and `IMPLEMENTS` edges are
   added for structural conformance — checked over the bounded set of (class in repo ×
   protocol in repo), not inferred from open-ended search. Zero-member protocols are
   excluded from the sweep (spike finding 2).
3. **Provenance on every upgraded edge.** `resolved_by: parse | types`, and on
   `IMPLEMENTS` edges `conformance: strict | structural`, so the atlas can always say
   which edges the cheap pass produced, which the typed pass added, and under which
   rule — and a detector's limitations text can say precisely what was and was not
   visible.
4. **Determinism is non-negotiable.** The pinned mypy version *and* the conformance
   rule's own version are folded into `analysis_config_hash` — changing either changes
   the edge set. An atlas built with resolution never compares equal to one built
   without it, and the same commit still always produces the same atlas. mypy runs
   non-incrementally (spike finding 4); the content-fingerprint cache above it is the
   only cache.
5. **Optional by construction.** An extra (`uv sync --extra resolution`); absent, the
   atlas is exactly today's. Indexing is the one-time cost per commit, so seconds-to-
   minutes of mypy on a large repository is acceptable where it buys correct counts —
   and cached by content fingerprint like everything else.

## How it is judged

Measured, not felt — and on more than one input:

- **Resolution rate**: unresolved references before vs. after, on all bundled examples
  and at least two real repositories (this one included).
- **The acceptance test that already exists**: on `audiobook-studio`, the
  sole-implementation detector must find the structurally-conforming adapters it
  currently cannot see, and the two repetition detectors' participants must not regress.
- **Determinism**: two runs on the same commit produce byte-identical atlases.
- **Cost**: indexing time per bundled example recorded before and after, so the price is
  a number in this document's follow-up rather than an impression.

## Phases

1. **Baseline** — count unresolved edges per bundled example; write the numbers down.
   Exit: the metric exists and is honest about what "unresolved" includes.
2. **Spike** — ✅ done (findings above). mypy answered both questions on
   `audiobook-studio`; go on mypy, pyright not needed.
3. **Integration** — the port, the enrichment pass, provenance, the config-hash fold.
   Exit: full suite green with the extra absent *and* present.
4. **Evaluation** — the measurements above, recorded here. Exit: the audiobook-studio
   acceptance test passes, or the plan is revised with what was learned instead.

## Measurements

Taken on the four bundled examples and on this project's own `src/`, before and after, with
everything else held fixed. Timings are the best of three whole `analyze()` calls, so they
include the AST parse, the metrics and the mypy build together — the number an indexing run
actually pays. `implements` counts `IMPLEMENTS` edges; `unresolved` counts
`unresolved-call` signals.

| Repository | Files | `implements` before → after | Provenance after | `calls` before → after | `unresolved` before → after | Seconds before → after |
| --- | --- | --- | --- | --- | --- | --- |
| audiobook-studio | 13 | 2 → 2 | 1 strict, 1 structural | 14 → 24 | 36 → 26 | 0.02 → 0.40 |
| boundary-review | 5 | 6 → 6 | 6 strict | 17 → 30 | 41 → 28 | 0.02 → 0.52 |
| speech-vendor | 16 | 6 → 6 | 6 from the parse (all inherit) | 21 → 29 | 29 → 21 | 0.02 → 0.48 |
| warehouse-sync | 14 | 2 → 2 | 2 from the parse (all inherit) | 11 → 14 | 26 → 23 | 0.02 → 0.43 |
| this project's `src/` | 75 | 26 → 30 | 30 strict | 929 → 1120 | 2217 → 2026 | 1.16 → 2.01 |

**The headline number did not move, and that is the honest result.** The heuristic already
found audiobook-studio's two structurally-conforming adapters, so the acceptance case was
never a count of two against a count of zero. What the typed pass changed there is what the
atlas can *say*: both edges now carry `resolved_by: types`, one at `strict` and confidence
1.0 and the other at `structural` and 0.9 — and the one at 0.9 is exactly `QwenSynthesis`,
the adapter that narrows `narrate`'s parameter. Where the heuristic offered a flat 0.8 to
both, a reader can now tell the pair the checker itself endorsed from the pair admitted by
a relaxed rule, and the finding's limitations can say which.

The negatives are correctly absent, which is the other half of the claim and the half a
count cannot show. `Voice` has no members and is skipped, so it gains none of the nine
classes that trivially satisfy it. Nothing in any example was wired to a protocol it does
not implement.

**The call edges are where the counts move.** Every example gains resolved calls and loses
unresolved-call signals — audiobook-studio 14 → 24 calls and 36 → 26 unresolved, this
project 929 → 1120 and 2217 → 2026 — because a method reached through a variable is a
target the parse can only guess at and the checker simply knows. Those edges feed fan-in,
blast radius and the call-chain metrics, so this is the part that lifts all three detectors
rather than one.

**One correctness result was only visible at scale, and it was severe.** Third-party imports
are left unfollowed for cost, which makes an imported base class `Any` — and a class with
`Any` in its ancestry answers *yes* to every member the checker is asked about. The first
run over this project's own `src/` reported **10,176** conformance pairs where the truth is
38, because every pydantic model in it satisfied every protocol in it. That failure is worse
than a wrong count: a boundary with two hundred implementations behind it does not get
reported wrongly, it drops out of the sole-implementation detector entirely, which is the
silent-miss failure this project treats as its worst. Classes whose ancestry the build did
not follow are now skipped outright — a class whose base is invisible cannot be judged — and
`test_a_class_with_an_unfollowed_base_is_never_judged` holds it.

**Cost.** Roughly half a second per bundled example and one extra second on this project's
75 files; the mypy build is the whole of it and is flat in the number of questions asked,
because the view is built once and every pair and every site is answered from it. Following
third-party imports instead would be correct without the skip above and costs 10s against
0.9s on this project — an order of magnitude to type code the atlas has no nodes for.
Indexing is once per commit behind the content-fingerprint cache, so this is affordable.
