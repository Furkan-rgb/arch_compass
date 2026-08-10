# Conventions

The rules of this codebase — where each is stated, and what enforces it.

An index, not a source. Where a rule already has a home, this points at it; where the
"Stated" column names this file, this is the home, because the rule was previously carried
only by commit messages and by the code that happened to follow it. "Enforced: convention"
is not a euphemism — it means nothing fails when the rule is broken, and a reader should
weigh it accordingly.

| Rule | Stated | Enforced |
| --- | --- | --- |
| **Layering and dependency direction.** `domain`, `application` and `ports` import no adapter, no framework and no driver. | `architecture.md` § Dependency direction; master plan invariants 17–18 | `tests/unit/test_boundaries.py` — an AST sweep per package, each asserting the directory still exists |
| **The evidence doctrine (§12.0).** The application decides what to look at; the model decides what it means; nothing the model writes is ever used as a key. Three stances: *shown, never fetching*; *may look, all recorded*; *assembled evidence only*. | master plan § 12.0 and invariant 22; the stances are tabulated in `system-tour.html` § 03 | `tests/unit/test_prompt_contracts.py`, `tests/unit/test_candidate_judgement.py`, `tests/unit/test_boundaries.py` |
| **The corpus decides what is worth detecting.** A finding candidate is a structural pattern that could make a policy relevant; the corpus is the specification for detection. | master plan § 8A.1; restated on `FindingPattern` in `domain/atlas.py` | convention |
| **Nothing decidable by counting.** An example repository must not let a reviewer reach the answer without reading the code. | `evaluation.md` § Example repositories | `tests/evaluation/` — one fixture test per example |
| **n = 1 is not a measurement.** A single live run is a sample, never a difference; a material flip needs a second agreeing sample. | `architecture.md` § Directions to weigh (they compose), direction E; `evaluation.md` § What a live run is read for | convention |
| **Positional binding; no model-authored identifiers.** Policies are presented in a fixed order without their IDs, answered one slot at a time, and bound back by position. Arity is the whole binding. | master plan § 8A.5, § 12.0, § 12.1 | `tests/unit/test_candidate_judgement.py` (six cases, including the short-reply repair); `tests/integration/test_reviews.py` |
| **Pinning at completion.** Everything a review depended on — case revision, atlas version, policy set, prompt identity — is pinned onto it when it finishes. | master plan § 5.1 and invariant 21; `system-tour.html` § 02 | `tests/integration/test_reviews.py`; `tests/unit/test_review_source.py` |
| **Decisions are append-only, and the review service never reads them.** The model judges; the team disposes. | `domain-model.md` § Triage; `persistence-model.md` § Standing state; the ledes of `domain/triage.py` and `application/triage.py` | append-only: `tests/integration/test_triage.py`, `tests/unit/test_standing_decisions.py`. The isolation half is convention — no guard forbids the review path importing triage |
| **Prompt contracts are content-addressed.** Identity is `name:vN:sha[:12]`; editing prose without a version bump still changes the identity, and with it the verdict cache. | `system-tour.html` § 04; `architecture.md` § Responsibilities (the `ReasoningTask` registry) | `tests/unit/test_prompt_contracts.py` |
| **Analyzer output changes bump the parser version.** A stored atlas that cannot answer a question the analyzer now answers is stale and re-analysed, not read with the answer missing. | the `PARSER_VERSION` comment in `adapters/analysis/ast_analyzer.py` | `tests/unit/test_analysis_equivalence.py` — the golden atlases, rewritten deliberately and never reflexively |
| **Modules are named for what they do.** No `utils`, `helpers`, `manager` or `core`; a name that needs the file open to be understood is the wrong name. | here | convention |
| **A docstring leads with the plain answer.** The first line says which question this module, class or function answers — not what it is called again. | here | convention |
| **Each package's `__init__` orients.** A one-line lede saying what the package is for, and a barrel re-exporting every name the package exposes, so a decomposition moves no import path. | here | convention |
| **Deliberate non-splits are argued in place.** A file left large on purpose says why in its lede, so the next reader does not re-litigate it. | here | convention |
| **Frontend: one sheet.** Every region of every page is the lowercase `sheet` from `components.tsx` and nothing else. | `frontend/src/components.tsx` | convention |
| **Frontend: `phoneFlush` for the panels that are not the sheet.** One name rather than the classes repeated, because the gutter value appears in it. | `frontend/src/components.tsx` | convention |
| **Frontend: the verdict colour families are spent nowhere else.** `--material` and `--cleared` carry judgement and nothing else; the accent never carries a judgement; a failure borrows the revision family rather than bringing a fourth hue onto the screen. | `frontend/src/styles.css` | convention |
| **Frontend: generated API types, no hand-written mirrors.** A hand-written mirror of a server contract is a second copy that no build step checks; one of them silently dropped two fields the day the server learned them. | `frontend/src/types.ts`; `scripts/generate_openapi_types.py` | `make api-types-check` (drift fails the build). That the mirror is never re-introduced is convention |
| **Frontend: the overflow sweep.** No text a model or a repository writes may widen the page; the guard list is the contract. | `frontend/src/overflow-guards.test.tsx` | itself — the test is the statement |
| **Frontend: `tsc -b`, never `tsc --noEmit`.** The frontend root `tsconfig.json` has `"files": []` and two project references, so `--noEmit` at the root typechecks an empty project and passes on anything. `pnpm run check` is `tsc -b && vitest run`; `pnpm run typecheck` is `tsc -b` alone. | here; `frontend/tsconfig.json` shows the mechanism | `make check` → `make frontend-check` → `pnpm run check`, run by CI |
