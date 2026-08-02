# ArchCompass

**Context-aware software architecture advice grounded in requirements, repository evidence, design policy and expected change.**

**[Try the live demo →](https://archcompass-99312935671.europe-west1.run.app)** — no signup;
pick a bundled example, run a review, ask it questions. Every visitor gets their own
workspace, and the model calls are rationed, so if a run is refused, the day's shared
budget is spent — come back tomorrow or run it locally.

ArchCompass is a software architecture advisor for developers and coding agents. It helps answer not only _how to implement a feature_, but **how the surrounding software should be structured so that it remains understandable and changeable over time**.

The project is built around a simple observation: AI-assisted coding is making it much easier to produce working code, but it does not remove the harder problem of managing complexity. A system can function correctly today while still being difficult to understand, expensive to modify and fragile under future requirements.

ArchCompass is intended to help with that problem.

---

## Why ArchCompass Exists

Modern coding agents can quickly generate features, patches and entire applications. They are often effective at making a test pass or connecting several components into a working flow.

However, a working implementation is not automatically a good design.

Questions such as these still require architectural judgement:

- Where should this responsibility live?
- Which concepts are stable, and which are implementation details?
- Is a new abstraction justified?
- Is provider-specific knowledge leaking into the rest of the application?
- How many parts of the system will need to change when this decision changes?
- Is complexity being removed, or merely spread across more files?
- Does an interface simplify the system, or only add another layer?
- Which future requirements are credible enough to design for now?

These decisions become more important as generating code becomes cheaper. The value increasingly lies in **containing complexity, limiting change amplification and making important relationships easy to discover**.

ArchCompass gives the developer and coding agent a persistent, evidence-backed architecture context in which to make those decisions.

---

## What ArchCompass Does

ArchCompass reviews the **boundaries** in an existing repository — the abstractions,
ports and indirections that already exist, and the knowledge those boundaries were meant
to contain — and decides, one at a time, whether each is earning its place given what you
are actually building.

Three structural detectors sweep the repository, covering both directions in which a
boundary can be wrong:

- **Indirection that hides nothing** — an abstraction with exactly one implementation
  behind it. It is what a deliberate port looks like, and also what premature abstraction
  looks like; counting cannot separate them.
- **Knowledge with no owner** — a constant stated in several modules at once, agreeing
  today by luck and liable to drift silently when one copy changes.
- **A concept that has escaped its package** — a vendor, format or backend named across
  modules that were given a boundary to reach it through and went around it instead.

None of these is a violation. An advisor that reported only the first would become an
advocate for copying; one that reported only the others would become an advocate for
abstraction. So each candidate is put to a model together with your case and the whole
policy corpus, and the answer is a verdict with its reasoning — *remove the boundary*,
*give this knowledge one owner*, or *leave it exactly as it is*.

For example:

> A task scheduler declares six boundaries and each has one implementation. The label
> format is fixed by a downstream system, SMS delivery ships next release, and a Postgres
> deployment is under discussion. Which of these boundaries should go?

ArchCompass reports on all six, names the three that absorb a change the case expects,
and recommends removing the three that absorb nothing. **Boundaries it clears appear in
the report alongside the ones it condemns** — a report listing only problems reads the
same whether every boundary was examined and cleared or none was ever looked at.

### Greenfield

Not yet built. The judgement stage takes a case, a candidate and the policies, and nothing
in it refers to a repository — so the same call works for a boundary that is merely
proposed. What is missing is the other source of candidates: today they come from parsing
code, and greenfield would need them stated in the case instead. See §4.1 of the master
plan for the shape and the one known obstacle.

---

## What ArchCompass Is Not

ArchCompass is not:

- A generic chatbot over a repository.
- A code generator.
- A linter that automatically labels patterns as violations.
- A universal maintainability scoring system.
- An autonomous refactoring agent.
- A tool that assumes more interfaces and modules are always better.
- A replacement for human architectural judgement.

A valid ArchCompass recommendation may be:

- Introduce a focused abstraction.
- Move a responsibility behind an existing boundary.
- Keep the implementation local.
- Preserve the current design.
- Delay the decision.
- Gather more information.
- Reject all proposed approaches and recommend another.
- Conclude that no architectural change is justified.

---

## Core Concepts

### ArchitectureCase

The persistent, revisioned context for one architectural decision: the problem and desired
outcome, requirements and quality attributes, constraints, non-goals, expected future
changes, confirmed facts and assumptions.

This is what makes an answer possible at all. The same abstraction is right in one case
and wrong in another, and the case is where that difference lives. A run against a case
saying *"SMS ships next release"* and one saying *"feature freeze, no variation planned"*
reach opposite verdicts on identical code — which is the whole point.

Every revision is preserved, and a review pins the exact one it ran against.

### RepositoryAtlas

A deterministic, versioned map of a Python repository: modules, classes, functions,
protocols and tests, with the imports, calls, inheritance, interface implementations and
references between them.

Built by parsing. The analysed repository is never imported, executed or modified, and the
same commit always produces the same atlas.

### FindingCandidate

A structural shape found in the atlas, with the evidence that establishes it — the
participants, what was measured, the relationships between them, and **what the detection
method could not see**.

A candidate is explicitly not a violation. Three detectors ship, covering both directions
of the catalogue: an abstraction with exactly one implementation (*indirection without
hiding*), a constant stated in several modules with no module owning it, and a concept
named beyond the package that owns it (the two shapes of *repetition without ownership*).

### PolicyCorpus

Reusable architectural guidance — intent, signals, diagnostic questions, consequences,
exceptions, examples and counterexamples.

The whole corpus is presented with every candidate. It is roughly 45,000 characters
against an input budget near 490,000, so there is no retrieval step, no ranking, and no
threshold that could quietly deny the advisor a policy that would have applied.

Policies are presented in a fixed order and answered by position. No policy identifier is
ever sent to the model or read back from it.

### BoundaryReview

An immutable record of one review: the case revision, the atlas version, the policies
presented, and every boundary examined with its verdict, reasoning and recommended
response.

Both outcomes are stored. A boundary the advisor cleared is the record that it looked.

### ReviewConversation

An append-only set of follow-up questions pinned to one review. Each turn puts the whole
review in front of the model — about 25,000 characters, so it fits comfortably — and the
answer comes back marking which boundaries it rests on, by position.

Every citation is resolved by ArchCompass from those positions. An answer grounded on
nothing is labelled as such rather than presented as though the review supported it.

---

## How It Works

```text
ArchitectureCase                     RepositoryAtlas
      │                                    │
      └────────────────┬───────────────────┘
                       ▼
        Detect finding candidates                  [deterministic]
        complete over the atlas — not sampled,
        not ranked, no model involved
                       │
                       ▼
      For each candidate, one model call:          [judgement]
        candidate + case + the whole policy corpus
                       │
                       ▼
             Verdict per boundary                  [judgement]
        material · reasoning · one bearing per
        policy, bound by position
                       │
                       ▼
        Compose and persist the review             [deterministic]
        assign BR-nnn references, resolve policy
        identity by position, render Markdown
                       │
                       ▼
       Ask what it needs to know                   [judgement]
        the one call that sees every verdict at
        once, so boundaries turning on the same
        unknown become one question
                       │
        ┌──────────────┴───────────────┐
        │ nothing to ask               │ questions outstanding
        ▼                              ▼
   The review concludes        The run stops and waits
                                       │
                            you answer; your answers
                            become a case revision
                                       │
                                       ▼
                            judge every boundary again,
                            then conclude
```

A review that is still asking is **not** a finished review. Judged against a case that has
not been written yet, verdicts are provisional in a way that is measured rather than
supposed: on the bundled `warehouse-sync` example, four of five moved once the questions
were answered. So they are stored, and they are not reported as findings until a second pass
has judged them against your answers. If you cannot answer, you can reveal them anyway —
labelled for what they are.

One rule shapes every stage of it:

> **The application decides what to look at. The model decides what it means. Nothing the
> model writes is ever used as a key.**

Which nodes, which policies, which candidate — all derivable, reproducible and testable,
and the application already holds the answer on both sides of the call. Whether a shape
matters given this case is judgement, and the only thing worth spending a model call on.

The third clause is the operational one. A model that must reproduce an identifier will
eventually reproduce it wrongly — not by inventing it, but by copying it imperfectly — and
the failure is silent because the value looks plausible. So identifiers never cross the
wire. Where a stage needs the model to point at something, it presents a bounded set and
takes back a position in it.

---

## Repository Mapping and Complexity

ArchCompass is influenced by the distinction between two broad causes of software complexity:

- **Dependencies:** code cannot be understood or changed in isolation.
- **Obscurity:** important information or relationships are difficult to discover.

These can result in:

- Change amplification.
- Increased cognitive load.
- Unknown dependencies and consequences.

ArchCompass cannot objectively measure how difficult code feels to a human. It therefore reports separate structural dimensions and explicit proxies rather than inventing one universal complexity score.

### Local structural metrics

Examples include:

- Physical lines.
- Logical statements.
- Branch count.
- Maximum nesting depth.
- Parameter count.
- Public API surface.
- Imported modules.
- Known incoming and outgoing calls.

### Dependency metrics

Examples include:

- Fan-in and fan-out.
- Direct dependencies and dependants.
- Forward and reverse dependency reach.
- Dependency depth.
- Cycles.
- Interface implementations.
- Associated tests.

### Change-amplification proxies

Examples include:

- Modules likely affected by a change.
- Implementations requiring coordinated updates.
- Configuration locations involved.
- Tests in the reverse dependency neighbourhood.

### Cognitive-scope proxies

Examples include:

- The size of the relevant dependency neighbourhood.
- The number of boundaries involved.
- Related configuration locations.
- Local control-flow complexity.
- Public API surface.

### Obscurity signals

Examples include:

- Wildcard imports.
- Dynamic imports.
- Module-level mutable state.
- Cyclic dependencies.
- Duplicate constants.
- Unresolved static calls.
- Public callables without documentation.
- Important behaviour distributed across multiple locations.

These are signals for architectural interpretation, not automatic design failures.

A module may be locally complicated while still improving the system by hiding that complexity behind a simple interface.

---

## Policies

Policies are Markdown, validated for metadata and sections, and **presented whole with
every candidate**.

There is no embedding model, no index and no retrieval step. The corpus is about 45,000
characters against an input budget near 490,000, so it fits several times over and ranking
only added a way to lose the passage that mattered (ADR 0013). If the corpus ever outgrows
one request, retrieval comes back as a deliberate change rather than an inherited one. A
policy that does not appear in a verdict did not apply, rather than never having been
shown.

```text
Policy Markdown
    → validate metadata and sections
    → present all of it, in a fixed order, with every candidate
    → one bearing back per policy, in that same order
```

The model never sees a policy identifier and never writes one. Identity is attached
afterwards from the position, so a mistyped or recalled-from-memory ID has no route into a
report.

---

## Evidence Discipline

Every verdict carries the reasoning that produced it, the policies that bear on it and how,
and **what the detection method could not see**. Detection limits are printed against each
boundary rather than once in a footer, because someone deciding whether to act on one
verdict needs them at the point of deciding.

Three things are structurally impossible rather than merely discouraged:

- **A citation to something that was not presented.** Policies and boundaries are answered
  by position, and identity is attached by ArchCompass afterwards.
- **A response of the wrong length.** The reply carries one entry per presented policy and
  the JSON Schema fixes the count. A short list would not lose one answer — it would shift
  every later answer onto the wrong policy and still parse — so the count is re-checked
  after parsing, with one repair round behind it.
- **A verdict reached before its reasoning.** A structured-output model fills a schema in
  the order it is declared, so the argument fields come first and the verdict last. Declared
  the other way round, a live run returned `material: false` beside a rationale concluding
  that removing the abstraction would cost nothing — and both halves validated.

```text
Deterministic code maps, measures, binds and validates.
Language models interpret, compare and advise.
```

---

## Review Output

A review produces JSON and Markdown from one report model, and both are stored with the
review itself.

A report contains:

1. The case title, problem and desired outcome.
2. Which policies were presented.
3. Every boundary examined, each with:
   - a `BR-nnn` reference, assigned by ArchCompass in detection order;
   - the participants in the boundary — the abstraction and its implementation, the
     modules sharing a constant, or the module whose concept escaped and where — located
     in the source;
   - the verdict — material or not — and the reasoning behind it;
   - a recommended response, **only** when material;
   - the policies that bear on it and how;
   - what the detection method could not see.

It contains no alternatives, no scenario analysis, no ADR and no implementation sequence.
A review judges boundaries that already exist; it does not weigh competing designs, so
there is nowhere in the report to put those and nothing to invent to fill them.

Read one with:

```bash
archcompass reviews show <review-id>
```

---

## Current Capabilities

- Persistent, append-only ArchitectureCase revisions.
- Python repository analysis using the built-in AST, stored as a versioned RepositoryAtlas.
- Structural nodes, edges, metrics and obscurity signals; bounded atlas queries and excerpts.
- Three structural detectors, both directions of the catalogue: abstractions with a
  single implementation, constants stated in several modules with no owner, and concepts
  named beyond the package that owns them.
- Judgement of each candidate against the case and the whole policy corpus, with policies
  bound by position and no identifier crossing the wire in either direction.
- Immutable BoundaryReview records, in JSON and Markdown.
- Follow-up questions pinned to one review, grounded in the boundaries they cite.
- Markdown policy parsing and validation.
- Configurable providers: local Ollama or hosted Google AI Studio, plus deterministic
  substitutes so the whole suite runs without a model.
- A browser workspace: pick a bundled example, read the review, ask about it, and explore
  the atlas graph.
- Three scored examples with known answers. `boundary-review` asks whether a boundary
  absorbs any variation at all; `speech-vendor` asks whether it is in the right place; and
  `audiobook-studio` exercises all three detectors at once, with both verdicts appearing
  under each repetition detector. `make demo` grades a live run against the first,
  `make eval-local` against all three.

Experimental. One limit is worth stating plainly rather than discovering:

- **Brownfield only.** Every candidate is parsed from existing code. Greenfield — a
  boundary judged from the case alone, before it is built — is architecturally reachable
  and unbuilt; see §4.1 of the master plan.

---

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A SQLite build supporting loadable extensions
- Optional: a local Ollama service for real-model consultations

Two providers ship with the build, and neither is implicit — a run always says which
model produced it:

```text
ollama    local models through Ollama
google    hosted Gemini models with a free tier
```

There is no model configuration file. Where a provider is reached, which variable carries
its credential and what its budgets are is stated in code, one descriptor per adapter, and
the only thing a run reads off disk is a `.env` — and only ever for a key. What is left to
choose is the part that actually varies: which provider, which model, and whether the model
reasons before answering.

A workspace chooses in the interface, from the model chip in the top bar, which offers only
models a reachable provider currently has. The choice is one row in that workspace's own
database and survives restarts. A command can override it for the length of one process:

```bash
archcompass --provider google --model gemini-3.6-flash review <case-id> --repo /path/to/repo
```

`--provider` and `--model` are given together or not at all, and while they are in force
the model is not the workspace's to change — a stored choice quietly overriding them would
make the flags mean nothing. This repository is also a workspace, so the Makefile makes the
choice for its demonstrations —

```bash
make web           # the workspace, reasoning with whatever it has chosen
make web-google    # the workspace, pinned to a hosted Gemini model
```

A deployment that cannot reach every provider says so with `ARCHCOMPASS_PROVIDERS`, a
comma-separated list of names: a hosted server has no local Ollama, and a chooser listing
one is a row that can only ever say "nothing is listening". `ARCHCOMPASS_OLLAMA_URL` moves
the local endpoint off loopback for the same kind of deployment.

Thinking is part of what is chosen rather than a setting beside it: `--thinking` requires
the model to reason before answering, `--no-thinking` forbids it, and omitting both leaves
it to the model. In the chip, a model that genuinely offers both appears twice — once each
way — and one that does not appears once. Those tokens are spent from the output allowance,
so a reasoning selection is given the larger of the two budgets; on a tight one the
structured answer is truncated, which fails validation rather than returning something
wrong.

The three are not two. Measured on `gemma4:26b` against the scored example: `true` took 510s
and scored 4/6, `false` took 40s and scored 3/6, and `null` took about 250s and scored 5-6/6.
That is why the models that do not genuinely offer a mode are not offered in it.

The provider's `context_window_tokens` controls Ollama's total context window (`num_ctx`),
including input and generated output. `max_output_tokens` separately caps generated output.

Pull the model you mean to reason with — a review needs one model and no other:

```bash
ollama pull gemma4:26b
```

Models are not downloaded automatically.

### Google AI Studio

A hosted alternative that needs no local model. The provider is there as soon as a key is:

```bash
echo 'GOOGLE_API_KEY=your-key-here' >> .env
archcompass --provider google --model gemini-3.6-flash review <case-id> --repo /path/to/repo
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey). `.env` sits at
the workspace root and is git-ignored; the provider's descriptor names the environment
variable and never holds the key itself. A variable already set in the environment takes
precedence over the file.

Two things differ from Ollama and are worth knowing:

- Gemini spends thinking tokens from the same allowance as `max_output_tokens`, so a
  stage can be truncated with a budget that would comfortably fit its JSON. The adapter
  reports that case by name rather than surfacing unparseable output.
- The free tier returns HTTP 429 once a quota is spent. Per-minute quotas clear on
  retry with backoff; a per-day quota exhausts the retry cap and fails the run.

---

## Installation

Clone the repository and install the locked environment:

```bash
git clone https://github.com/Furkan-rgb/archcompass.git
cd archcompass

uv sync --locked
uv run archcompass init
```

The bundled policy corpus is ready to use — policies are read from their sources whenever
they are asked for, so there is nothing to build.

State is stored locally under:

```text
.archcompass/archcompass.db
```

---

## Quick Start

### The fastest path: a bundled example

Every bundled example ships a written case and a repository to run it against, so a fresh
workspace can produce a real review without writing a case first.

In the browser workspace:

```bash
uv run archcompass web
```

Open **Reviews**, pick an example, and it indexes the repository, creates the case, judges
every boundary, and shows the report with a box to ask questions about it.

Or grade a run against known answers:

```bash
make demo          # Google, about two minutes
make demo-local    # Ollama
make eval-local    # all three examples, on Ollama
```

`eval/cases/boundary-review` has six boundaries the detector cannot tell apart and a case
that makes three of them justified. A run that clears all six is an abstraction generator;
one that condemns all six is an abstraction destroyer. The score separates those from an
advisor.

`eval/cases/speech-vendor` is the harder half. Every one of its six boundaries stands in
front of a change that is genuinely coming — a second speech vendor is under contract — so
clearing all six is the *plausible* mistake there. Three are drawn at the vendor edge; three
are vendor-shaped seams cut into modules that have no other reason to know a vendor exists.
Its case names no defect, no fix and none of the classes at issue, so the score measures
judgement rather than reading.

`eval/cases/audiobook-studio` is the hardest, and the only one that exercises all three
detectors together. Both verdicts appear under each repetition detector: for a duplicated
constant and for a scattered vendor name alike, one instance is a real finding and one is
not, and only the case says which. Its adapters conform structurally rather than
inheriting and widen the signatures their ports leave narrow, so a detector that reads a
port by the spelling of its base class finds nothing here and reports it as a clean bill
of health.

### Review your own repository

Index it, write a case, review it:

```bash
uv run archcompass repo index /path/to/repository
uv run archcompass case create --from your-case.yaml
uv run archcompass review <case-id> --repo /path/to/repository
```

The case is the part that matters. It is what tells a justified boundary from an
unjustified one, so `expected_future_changes`, `non_goals` and `confirmed_facts` do more
work here than anything else you write.

You do not have to write it first, though. A review will run against a repository alone and
come back asking for what would settle the verdicts it could not settle — so the case is
something you end up with rather than something you start with. When a run stops to ask,
answer into the fields its questions name and carry it on:

```bash
uv run archcompass case update <case-id> --from answers.yaml
uv run archcompass review <case-id> --repo /path/to/repository --answers <review-id>
```

Both passes are kept, each pinned to the case revision it judged, so you can see exactly
what your answer changed.

Print the stored review instead of its Markdown:

```bash
uv run archcompass review <case-id> --repo /path/to/repository --json
```

### Ask about a review

```bash
uv run archcompass reviews list
uv run archcompass reviews show <review-id>
uv run archcompass reviews ask <review-id> "Why was the storage boundary left alone?"
uv run archcompass reviews history <review-id>
```

Each answer names the boundaries it rests on. An answer grounded on none of them says so
rather than presenting itself as something the review supports.

### Explore the atlas

```bash
uv run archcompass atlas summary /path/to/repository
uv run archcompass atlas hotspots /path/to/repository \
  --metric reverse-dependency-reach
```

The browser workspace draws the same data as a graph under **Repositories**.

### Update a case

```bash
uv run archcompass case update <case-id> --from update.yaml
uv run archcompass case history <case-id>
```

Revisions are append-only, and a review records the exact one it ran against.

### Inspect policies

```bash
uv run archcompass policies list
uv run archcompass policies show <policy-id>
```

---

## Hosted demo

The same application deploys as a public demo from one container. `ARCHCOMPASS_HOSTED=1`
switches on the three things a public server needs that a local workspace does not:

- **A workspace per visitor.** A session cookie names each visitor's own workspace on the
  container's ephemeral disk, so two people trying the demo at once never see each other's
  cases, reviews or model choice.
- **A demo repertoire, not a filesystem.** Browsing the server's folders is refused, and
  only the bundled example repositories can be indexed and reviewed.
- **A daily budget.** The model-spending endpoints are rationed per session and per
  instance, so one visitor cannot spend the day's free-tier quota.

`archcompass web` reaches none of this — locally, nothing changes.

```bash
make docker-build   # builds the image and checks the container answers
```

[docs/deploy.md](docs/deploy.md) has the Cloud Run commands: `ARCHCOMPASS_PROVIDERS=google`
so the picker never offers an Ollama that is not there, and `GOOGLE_API_KEY` from Secret
Manager — the hosted entry point refuses to start without a working provider.

---


## Architecture

ArchCompass follows an inward dependency direction:

```text
Presentation
    → application services and workflows
        → domain models and ports
            ← adapters
```

The main responsibilities are:

- `domain/` — validated application concepts, explicit errors, and the finding
  detectors, which are pure derivations over an atlas rather than ports.
- `ports/` — interfaces for persistence, repository analysis, retrieval and reasoning.
- `application/` — one module per job: `reviews`, `review_conversations`,
  `review_rendering`, `cases`, `bundled_cases`, `repository_index`, `atlas_queries`,
  `atlas_freshness`, `policies`.
- `adapters/persistence/` — SQLite storage and migrations.
- `adapters/analysis/` — AST analysis, graph metrics and deterministic queries.
- `adapters/retrieval/` — policy parsing and the bundled method primer.
- `adapters/models/` — the provider-neutral reasoning stages (`structured.py`), the
  Ollama and Google transports that carry them, and deterministic test providers.
- `presentation/cli/` — command-line input and output.
- `presentation/web/` — the local FastAPI adapter and the React workspace bundle.
- `bootstrap.py` — the composition root and only location that selects concrete adapters.

The domain and application layers do not depend on Typer, HTTPX, SQLite or AST implementation details.

---

## Development

Run all standard checks:

```bash
make check
```

Grade a live run against known answers:

```bash
make demo          # Google, about two minutes
make demo-local    # Ollama
```

Drive the built workspace in a real browser:

```bash
make test-browser
```

Other targets:

```bash
make eval          # fixture checks, no model
make test-ollama   # live local-model tests
make test-google   # live hosted tests; spends free-tier quota
make build
```

`make check` uses deterministic substitutes throughout and needs no model. Anything that
calls a live service sits outside it, because a failure there is a measurement about the
model rather than a broken build.

---

## Project Direction

The long-term goal is for ArchCompass to become a persistent architectural reasoning layer around software development.

The route there is a product observation as much as an engineering one: architecture
advice earns its keep at the moment a boundary decision is being made, and there are two
such moments — a pull request is open, or a coding agent is about to write code. A
whole-repository review read outside any decision is how the mechanism is demonstrated
and evaluated; the same review, arriving at one of those moments, is the product. The
sequence, argued in full in the master plan (§6C, §17):

1. **Elicitation — the review asks for the case** *(current)*. The case is what makes
   judgement possible, and also the tax nobody pays before seeing value — so invert it.
   A review may run against a thin case; each verdict states the circumstance it turned
   on, and the review hands back the questions whose answers would settle its verdicts,
   each naming the boundaries that turn on it. Answers become ordinary user-authored
   case revisions through the existing revise-and-review loop, so the case accretes from
   use instead of being authored up front. No new model calls: the judgement and
   overview stages already run, and elicitation extends what they return.
2. **Greenfield candidates** — boundaries stated in the case instead of parsed from
   code, judged before they are built (§4.1 of the master plan). Elicitation is also how
   a greenfield case — thin by definition — thickens.
3. **Diff-scoped review** — the pull-request moment. A diff carries a handful of
   candidates rather than a repository's worth, so cost is bounded by the change, and a
   boundary is judged once, when it is introduced, rather than re-litigated on every
   run.
4. **Coding-agent integration** — an MCP surface with two calls: consult a proposed
   boundary before the code exists, review a diff after it is written. The consumer of
   architecture advice at scale is increasingly the agent about to create the boundary.
5. **Decision lifecycle and architectural memory** — acceptance and supersession of
   decisions, then drift, git co-change evidence and decision history. Memory compounds
   only once the advisor is in the loop, which is why it is last rather than least.

### Detection roadmap

Detection today runs three detectors across the two catalogue directions. These are
candidates for the next ones — experiments, not commitments. The bar is deliberately high:
detection is a complete sweep with no ranking, so every detector adds a model call per
match and a line in every report, and a fuzzy detector dilutes the signal a precise one
carries. Each item below either maps to a policy already in the corpus or closes a gap a
current detector admits to.

#### Ranked for adoption

A separate question from which detector comes next: what would have to improve before an
engineering organisation could run this on its own repository. Most binding first — and
the list is about detection's surroundings more than its catalogue, because the bottleneck
is not how many shapes detection can see.

1. **Scope, before ranking.** Detection is a complete sweep and judgement is one model
   call per candidate, so cost and report length grow with the repository. On the bundled
   examples that is exact and affordable; on a monorepo it is neither — the duplication
   detector alone would fire on every shared constant name. The remedy that preserves the
   no-ranking principle is scope: review one package, one subsystem or one diff
   *completely*, rather than the whole repository approximately. This is why diff-scoped
   review sits on the product path above rather than among the directions further out.
2. **Verdicts that survive a rerun.** Organisations run tools repeatedly; today every run
   re-judges every boundary, which multiplies cost and lets an unchanged boundary flip
   verdicts between Mondays. A stored verdict should hold while the candidate, the case
   revision and the policy corpus are unchanged — and a team must be able to accept a
   boundary so it appears as accepted rather than re-litigated in every report (the
   decision-lifecycle step of the product path above).
3. **Edge resolution** (the fidelity item below). Real codebases wire implementations
   through registries, dependency-injection containers and framework decorators that
   static inheritance counting cannot see. Every unresolved edge is a candidate that is
   wrong in a specific, checkable way — and one confidently wrong *only one
   implementation*, shown to the engineer who wrote the second one, is how a trial ends.
4. **A second language.** Python-only is the hard ceiling on who can adopt at all. It
   ranks after fidelity rather than before, because judgement never sees a parse — the
   language surface is contained in the atlas — and a detector set that has not earned
   trust in one language is not improved by being wrong in two.
5. **Evidence from history** (the architectural-memory step of the product path).
   Modules that always change together are the evidence class a skeptical team finds
   hardest to argue with, because it is their own history rather than a theory about
   their code.

Deliberately *not* on this list: more detectors — each one adds a model call per match,
and precision earns adoption where coverage does not. Implementations that live in
another repository need no detector fix either: the limitations printed on the candidate
name that blind spot, and a `confirmed_facts` entry in the case settles it at judgement
time. And the split itself — deterministic detect, model judge, nothing model-written
used as a key, limits stated per boundary — is the part an organisation's reviewers can
accept, and the part to keep.

**Sharpen what already runs — cheapest, reversible:**

- [ ] Attach already-computed atlas signal — cycle membership, instability,
      reverse-dependency reach — to existing candidates as measurements, improving the
      model's judgement with no new model calls.

**New detectors — a policy exists and the signal is already computed:**

- [ ] Cyclic dependency (`keep-dependencies-acyclic`). The atlas already finds cycles, and
      an accepted cluster and a layering violation look identical to counting.
- [ ] A stable module depending on an unstable one (`depend-toward-stability`), derivable
      from the fan-in and fan-out already measured.
- [ ] A pass-through / tramp parameter, threaded through a call and never used
      (`avoid-pass-through-parameters`).
- [ ] A shallow module: a wide interface with little hidden behind it
      (`prefer-deep-modules`, `keep-interfaces-simple`).

**Fidelity — research:**

- [ ] Evaluate a type checker (pyright/mypy) as an edge-resolution backend, to cut
      unresolved static calls and lift every detector at once. A linter or type checker may
      inform detection, never a verdict, and its rule identity never reaches the model.

**Known blind spots — harder, and noisier:**

- [ ] Duplicated knowledge with no shared name — the same rule written twice in different
      words, which the name-based detector cannot see (structural clones).
- [ ] A concept that leaked without carrying its name.
- [ ] Implementations bound dynamically through a registry or factory, which static
      parsing cannot resolve.
- [ ] Git co-change / churn coupling — modules that always change together, invisible to a
      single snapshot (the architectural-memory step of the product path).

Further out, beyond the numbered product path:

- Implementation-plan review.
- Comparison between repository atlas versions.
- Revisit-trigger evaluation.
- Additional programming languages — deliberately last: a detector set that has not
  earned trust in one language is not improved by being wrong in two.

These are directions, not current capabilities.

ArchCompass will continue to avoid a universal complexity score and will not treat design policies as automatic enforcement rules.

---

## Documentation

- [Master plan](docs/master-plan.md)
- [Product definition](docs/product-design.md)
- [Architecture](docs/architecture.md)
- [Domain model](docs/domain-model.md)
- [Repository atlas](docs/repository-atlas.md)
- [Atlas metrics](docs/atlas-metrics.md)
- [Policy format](docs/policy-format.md)
- [Persistence model](docs/persistence-model.md)
- [Web workspace](docs/web-workspace.md)
- [Evaluation methodology](docs/evaluation.md)

The master plan is the authority on direction. Sections describing the superseded
consultation path are marked as such in place, so what is current and what is history stay
distinguishable.

---

## License

ArchCompass is licensed under the Apache License 2.0.
