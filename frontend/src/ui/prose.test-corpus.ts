/**
 * Every recorded judgement long enough for the block cap in `sentences()` to do anything, and
 * nothing else.
 *
 * `ui/prose.test.tsx` drives its packing property from this rather than from a written pair.
 * The property under test — an argument never opens on its tallest block — is a claim about
 * `pack`, so the population it has to hold over is every string `pack` is ever handed. The
 * fixture this replaces held two of the nine, which is enough to catch the mutation those two
 * were chosen for and blind to any that spares them: the other seven pack differently, three
 * of them take the opening ceiling's escape, and the tallest block in the set belongs to a
 * string neither of the two was.
 *
 * **How this was extracted, so the next reader can redo it rather than trust it.** Copy
 * `.archcompass/workspace.sqlite3` and open the copy read-only. The judgements live in two
 * places and both are needed: `core_review_snapshots.review_json` carries 148 findings inside
 * seven sealed reviews, and `core_finding_cache.finding_json` carries 231 more that were
 * reused rather than re-judged. Take `reasoning` off all 379 and drop the four exact
 * duplicates, which leaves the **375** every count in `ui/prose.tsx`, `ui/prose.test.tsx` and
 * `docs/design-system.md` is over. Hand each one to the real `sentences(source,
 * Number.MAX_SAFE_INTEGER)` — the cut with no cap — and keep the ones that come back with more
 * than `MOST_PARTS` sentences. **Nine do**, and they are these, in length order.
 *
 * **Why the strings are checked in rather than read at test time.** Reading the database from
 * a unit test would keep this current for free, and it costs two things that are worse than
 * staleness. The workspace is a developer artifact: it is not in the repository, it is not in
 * CI, and a suite that skips itself when a file is absent is a suite that is green on the one
 * machine that matters least. And a test whose fixture changes every time somebody runs a
 * review is a test that cannot be bisected — the property would start failing on a string
 * nobody can reconstruct. So the corpus is pinned here, with the method above written down, and
 * a re-extraction is a deliberate edit to this file.
 *
 * **What it costs, measured rather than estimated.** 12,170 characters over nine strings —
 * the sum of the nine `chars` below, each of which `ui/prose.test.tsx` asserts against the
 * string beside it, so the total is checked and not counted by eye.
 *
 * This paragraph used to add the array's size in bytes, and then argue that a byte count moving
 * when somebody edits the comment stating it "is a number that cannot stay true". The argument
 * was right and the number was wrong — off by 556, because it counted the type annotation the
 * definition it names does not include. Both facts point the same way, so the figure is gone
 * rather than corrected: what a reader needs here is the 12,170, which a test resolves, and the
 * source is on screen for anyone who wants to know how much room it takes.
 *
 * `pack` is O(blocks x sentences squared) — six by nineteen at the longest of these — so the
 * whole set is packed inside the test's own noise. `pnpm vitest run src/ui/prose.test.tsx`
 * reported its 33 tests at 75ms, 37ms, 43ms and 53ms over four runs on one machine, and a
 * spread of 38ms is wider than anything nine strings add to it; a single figure here would be
 * a number about which run it was taken on. Nothing in this file is imported by the
 * application, so none of it reaches the bundle.
 *
 * Six are material and three are cleared. **None is held**, and that is a fact about the
 * corpus worth keeping beside the phone entry in `docs/known-defects.md`: the arguments a held
 * finding can carry run 156 to 971 characters, so the block cap and the scroll that entry
 * prices are properties of two different populations.
 */
export const OVER_CAP: readonly {
  /** The candidate the judgement is about, for a failure message that names something. */
  readonly subject: string;
  /** The verdict it reached, which decides whether the row it opens carries a hinge. */
  readonly verdict: "material" | "cleared";
  /** Characters in the recorded string, asserted so a bad paste cannot pass silently. */
  readonly chars: number;
  /** Sentences the uncapped cut finds in it — the reason it is in this file at all. */
  readonly sentences: number;
  readonly source: string;
}[] = [
  {
    subject: "NarrationPreparationProvider",
    verdict: "material",
    chars: 963,
    sentences: 7,
    source:
      "The detection identifies NarrationPreparationProvider, an abstraction with a single " +
      "implementation (OllamaProvider) and three references. The codebase evidence and answers " +
      "confirm that this abstraction was deliberately introduced as a port boundary for " +
      "upcoming hosted providers, so it is not premature. However, the evaluation must " +
      "determine if this structure costs more than it earns. The implementation exposes " +
      "provider-specific details and uncontained leakage, but the abstraction itself serves as " +
      "an intentional port boundary. Looking at the policies, delay-premature-abstraction " +
      "cautions against abstractions without variation, but here variation is committed. " +
      "However, another finding indicates that provider details leak across boundaries without " +
      "containment. Because the abstraction has a single concrete implementation in this " +
      "snapshot and ties into uncontained provider specifics, the cost of maintaining the " +
      "indirection outweighs its current earnings.",
  },
  {
    subject: "AtlasFreshnessChecker",
    verdict: "cleared",
    chars: 967,
    sentences: 10,
    source:
      "AtlasFreshnessChecker is a single-implementation protocol (implemented by " +
      "AtlasFreshnessService) used to ensure that a repository atlas is fresh before performing " +
      "analysis or querying. Although it has a single implementation in this repository, it " +
      "acts as a deliberate port boundary separating domain query/service orchestration from " +
      "concrete freshness checking mechanisms, which may vary or be substituted in tests or " +
      "alternate runners. However, measurements show 0 test doubles and 0 test references to " +
      "the abstraction itself. Let's verify whether it's cleared or material. Wait, policy " +
      "delay-premature-abstraction permits safety/testing/platform boundaries to justify one " +
      "implementation. Here, it is a port boundary between analysis/queries and freshness " +
      "checks. Is it material or cleared? Let's check if it earns its keep or costs more than " +
      "it earns. It's a very simple protocol with 1 method, keeping responsibilities cleanly " +
      "separated. Therefore, it is cleared.",
  },
  {
    subject: "RevisionCalculator",
    verdict: "cleared",
    chars: 1042,
    sentences: 9,
    source:
      "The candidate archcompass.ports.capabilities.RevisionCalculator is a protocol defining a " +
      "capability used in the review workflow (calculate_delta_node). It has a single " +
      "implementation in this repository (DeterministicRevisionCalculator), and 0 test " +
      "references or test doubles. Under policy delay-premature-abstraction, an abstraction " +
      "with a single implementation and no test doubles/references is a signal of premature " +
      "abstraction, unless it falls under an exception like a platform/testing/architecture " +
      "boundary or ports/adapters architecture separation. However, looking at the architecture " +
      "of archcompass, ports.capabilities define the boundary between the workflow engine and " +
      "analytical capabilities. Is this abstraction earning its place? It decouples the " +
      "workflow node graph from the specific deterministic delta calculation logic, allowing " +
      "future alternative calculators (e.g. LLM-based or heuristic) without changing workflow " +
      "nodes. Thus, it acts as a clean port boundary in a ports-and-adapters architecture. " +
      "Therefore, it is cleared.",
  },
  {
    subject: "PolicyStore",
    verdict: "material",
    chars: 1095,
    sentences: 8,
    source:
      "PolicyStore is a port abstraction with only one concrete implementation " +
      "(MarkdownPolicyStore), zero test doubles, and zero test references directly to the " +
      "abstraction in this repository. Under delay-premature-abstraction, an abstraction " +
      "without a second committed implementation or concrete testing need adds interface " +
      "overhead without earning its place. However, PolicyStore sits at a clean architectural " +
      "boundary where persistence format (markdown files) could theoretically be swapped or " +
      "tested, but here it is a single-implementation port where the implementation and the " +
      "port methods are tightly coupled to markdown file staging and publishing. Wait, let's " +
      "evaluate whether it's material or cleared. The candidate is a sole_implementation. Under " +
      "policies like delay-premature-abstraction and prefer-deep-modules / " +
      "contain-dependencies, port abstractions with a single implementation often cost more " +
      "than they earn unless they insulate volatile dependencies or enable testing. Here there " +
      "are no test doubles and no other implementations. Therefore, it is material (costs more " +
      "than it earns).",
  },
  {
    subject: "EdgeResolver",
    verdict: "cleared",
    chars: 1116,
    sentences: 8,
    source:
      "EdgeResolver is an abstraction with exactly one implementation (MypyEdgeResolver) in the " +
      "repository, used as an optional oracle for resolving types via mypy when the resolution " +
      "extra is installed. It isolates mypy dependency and optional features from core AST " +
      "analysis. Although it has a single implementation and 0 test references, it serves a " +
      "clear architectural platform/optional boundary purpose (as noted in policy exceptions " +
      "for platform boundaries and optional dependencies). However, under the " +
      "delay-premature-abstraction and single-implementation analysis, is it material? Wait, " +
      "let's review policy: 'A safety, testing, or platform boundary can justify one " +
      "implementation — an interface that exists so effects can be substituted in tests, or so " +
      "a platform-specific detail stays isolated, is earning its keep from day one.' " +
      "MypyEdgeResolver isolates a heavy, optional dependency (mypy) behind a protocol so that " +
      "the core analyzer works without mypy being installed at all. Therefore, the port " +
      "successfully isolates an optional heavy dependency and keeps the analysis code decoupled " +
      "from mypy. It is cleared.",
  },
  {
    subject: "scattered_concept over 'ollama'",
    verdict: "material",
    chars: 1322,
    sentences: 10,
    source:
      "The structure scattered_concept identifies that 'ollama' is referenced across multiple " +
      "modules outside its owning package. Looking at the code, modules like cli.py, config.py, " +
      "and benchmarking scripts directly reference 'ollama' and check provider-specific " +
      "capabilities (like Ollama's thinking mode or base URL/models), which violates the " +
      "abstraction boundary of the preparation providers and leaks implementation details of a " +
      "volatile dependency outside its containment layer. However, since this is an early " +
      "review with no prior decisions recorded, and configuration/providers often involve " +
      "naming concrete backends at composition/CLI boundaries, we must consider whether this " +
      "costs more than it earns or is cleared by setup/composition conventions. Wait, let's " +
      "look closer at the policies: hide-implementation-details and contain-dependencies both " +
      "point out that provider-specific details leaking across modules create tight coupling. " +
      "But is it material or cleared? Let's check if there is an explicit instruction or if " +
      "it's material. The candidate pattern is scattered_concept. Let's evaluate if the " +
      "scattered naming costs more than it earns. It couples CLI options and config directly to " +
      "ollama strings, making adding other providers require touching multiple files. " +
      "Therefore, it costs more than it earns (material).",
  },
  {
    subject: "InitialCandidateSelector",
    verdict: "material",
    chars: 1688,
    sentences: 13,
    source:
      "archcompass.ports.capabilities.InitialCandidateSelector is a protocol port with a single " +
      "implementation (ChangedAndNewCandidateSelector) in the repository, 0 test doubles, and 0 " +
      "test references to the abstraction itself. Under the delay-premature-abstraction and " +
      "prefer-deep-modules policies, this single-implementation abstraction adds interface and " +
      "file overhead without containing multiple variants or hiding complex mechanics. However, " +
      "examining the capabilities file and workflow graph shows it is part of a clean hexagonal " +
      "port architecture where workflow capabilities are explicitly defined as protocols to " +
      "decouple the workflow orchestration from default heuristics. But given the strict " +
      "policies against premature abstraction when no variation or test double exists, does it " +
      "cost more than it earns? Wait, let's look at the other capability ports. Are they all " +
      "protocols? Yes, the entire archcompass architecture uses Python `Protocol` definitions " +
      "for capabilities, injected into workflow nodes. If every capability port is a protocol, " +
      "InitialCandidateSelector is part of a uniform architectural pattern supporting test " +
      "doubles or alternative strategies (e.g., in tests or future extensions). But wait, the " +
      "case answer says 'Im not sure what it is exactly' for a different model, but here we are " +
      "judging InitialCandidateSelector. Is there any uncertainty requiring a hold? No, the " +
      "evidence is clear: 1 implementation, no test doubles, no test references. Under " +
      "delay-premature-abstraction, an interface with one implementation and no credible second " +
      "variant or test double is a sole implementation sole-instance candidate that costs more " +
      "than it earns. Therefore, it is material.",
  },
  {
    subject: "ReviewExecutionStore",
    verdict: "material",
    chars: 1838,
    sentences: 14,
    source:
      "ReviewExecutionStore is a protocol interface defined in archcompass.workflow.service " +
      "with exactly one implementation in the repository (SQLiteReviewExecutionRepository). " +
      "There are no test doubles offering its methods and no test references pointing directly " +
      "to the abstraction protocol itself in test modules. According to the policies on " +
      "delay-premature-abstraction and different-layer-different-abstraction, an abstraction " +
      "with a single implementation and no substitution or alternate variance adds an " +
      "indirection hop without earning its place. However, looking at the architectural " +
      "patterns in this service layer (such as separating workflow coordination from execution " +
      "persistence), this boundary might be intended as an isolation seam or future port. " +
      "Without team intent regarding whether this is a deliberate architecture port for future " +
      "adapters or premature abstraction, the structure leans toward material cost unless " +
      "justified by expected multiple implementations or port boundaries. Let's weigh if it's " +
      "cleared or material. Wait, if it's a port boundary where only one adapter exists today, " +
      "the dossier notes: 'an abstraction may be deliberate at a port boundary where only one " +
      "adapter exists today.' But policy-wise, without test doubles or second implementations, " +
      "it costs an extra layer. Let's judge it as material under delay-premature-abstraction or " +
      "cleared if it's a standard architectural port. Wait, the prompt says: 'Judge whether " +
      "this detected structure costs more than it earns. Use the supplied evidence and case, " +
      "and the repository where it can settle something they cannot.' Let's provide a clear " +
      "verdict. Since there's only one implementation, no test doubles, and it mirrors the " +
      "sqlite execution lifecycle closely, it represents premature abstraction or an " +
      "unnecessary protocol layer. Therefore, it is material.",
  },
  {
    subject: "SynthesisProvider",
    verdict: "material",
    chars: 2139,
    sentences: 19,
    source:
      "The abstraction SynthesisProvider has a single implementation (QwenSynthesisProvider), " +
      "and policy 3 states to delay abstractions until variation is credible. The case " +
      "explicitly notes that this single implementation is an intentional port boundary for " +
      "future providers on a committed roadmap, but policy 3 still requires that an abstraction " +
      "must earn its place by removing or containing present complexity. However, the presence " +
      "of the single implementation without an active second variant violates policy 3, or more " +
      "directly, policy 1 and policy 6 are implicated, but policy 3 directly targets " +
      "single-implementation abstractions. Wait, looking at policy 3: 'An abstraction must earn " +
      "its place by removing or containing present complexity'. Here, the abstraction has " +
      "dependants_of_abstraction = 2 references. Does it earn its place? The evidence and " +
      "candidate show sole_implementation. Let us check policy 3 signals: 'An interface has one " +
      "implementation, one caller, and no credible second variant.' Here it has 2 references. " +
      "But policy 3 explicitly allows a genuinely committed second case. The case says: 'The " +
      "single implementation is an intentional port boundary established for future narration " +
      "providers on a committed roadmap.' If the roadmap is committed, policy 3's exception " +
      "applies ('A genuinely committed second case may be designed for before it is built'). " +
      "Let us check other policies: Policy 1 ('Hide implementation details behind the owning " +
      "boundary'). The candidate structure hides Qwen details behind SynthesisProvider, which " +
      "has 2 references. Policy 1 positive example: 'A speech-provider module exposes a voice " +
      "catalogue...' which matches SynthesisProvider. Therefore, the structure earns more than " +
      "it earns because it successfully hides provider implementation details (Policy 1) and " +
      "implements a committed port boundary (Policy 3 exception). Thus, it is material and " +
      "costs less than it earns, or wait—does it cost more than it earns? The prompt asks: " +
      "'Judge whether this detected structure costs more than it earns.' Since it correctly " +
      "isolates a volatile dependency (Qwen) on a committed roadmap, it earns its place.",
  },
];

/**
 * The narrowest column the model's paragraph is ever drawn in, in CSS pixels.
 *
 * A phone at 390px, less the section's own padding and the page's. It is a measured rectangle
 * and not arithmetic over the padding utilities: `tests/browser/test_mobile.py` drives the real
 * bundle in an emulated iPhone 15 at 390x844, opens a finding, and reads `clientWidth` off the
 * paragraph — **324**, which is where this number comes from and where it can be taken again.
 * The same test puts `WIDEST_UNBREAKABLE_TOKEN_PX` of qualified name into that block and asserts
 * the ink stays inside the column. Run it against a bundle built with the block's anywhere-break
 * deleted and it reads **542 against 324** — the constant below, reached through the shipped
 * page rather than through a measuring rig.
 */
export const PHONE_COLUMN_PX = 324;

/**
 * The widest thing the model has ever written that a line breaker may not break, in CSS pixels.
 *
 * `(src.audiobook.preparation.providers.base.NarrationPreparationProvider)` at **541.7px** — 71
 * characters, brackets included, because UAX #14 forbids a break after an opening bracket and
 * before a closing one, so the widest unbreakable run is the name plus the brackets round it
 * rather than the name. It is the floor under the measure `ModelProse` sets, and
 * `features/review/finding-detail.test.tsx` argues that at length: how it was measured, why it
 * is a figure about Onest specifically, and why the two 74-character names in the corpus are
 * wider and still not candidates for it. The number lives here because a measurement kept in
 * two files drifts, and the second copy is what tells you it drifted, after.
 *
 * **What it costs when a block cannot break inside it**, which is the half `ui/prose.test.tsx`
 * needs and which is a different measurement. Render all 375 strings through the real
 * `ModelProse` in a headless Chromium, serving the built stylesheet so the face is the shipped
 * `onest.woff2`, with both Onest weights and IBM Plex Mono asserted through
 * `document.fonts.check` before anything is read — `font-display: swap` otherwise answers with a
 * fallback whose zero is 0.6299em and every width comes out five per cent wrong. At a
 * `PHONE_COLUMN_PX` column the shipped component overflows on **0 of 375** strings and its
 * widest line box is exactly 324.00px. Take the anywhere-break off the block and **48 of the
 * 375** overflow their column, the worst by **218px**, and the widest line box drawn is
 * 541.70px — this constant, arrived at from the other end and by a different route.
 */
export const WIDEST_UNBREAKABLE_TOKEN_PX = 541.7;

/**
 * The recorded string that opens on its own wall, which is the condition the packing guarantee
 * carries and could not be written down while nothing held a witness to it.
 *
 * `pack` promises that a long argument never opens on its tallest block, and it can only keep
 * that promise where it runs — on the nine strings above, which is where the model wrote more
 * sentences than `MOST_PARTS` allows. Under the cap every boundary is cut, so the blocks *are*
 * the model's sentences and there is no packing decision left to make: the opening block is the
 * first sentence, and no rule short of cutting inside a sentence can make it shorter.
 *
 * This is that case at its worst. 673 characters, two sentences, and the first of them is 524
 * of those characters — **seven line boxes against two** at the 617.12px measure, and **17
 * against 4** in a phone's 324px column. Counted the same way every other line figure in these
 * files is: all 375 strings through the real `ModelProse` in a headless Chromium against the
 * built stylesheet, a Range per character of the block's rendered text, clustered on the
 * vertical centre of each rect at a 0.6px tolerance, one cluster to a line.
 *
 * **It is not the only one and it is not the worst block.** Two strings open on seven lines —
 * this one and a 1,235-character six-sentence judgement that draws 7/3/3/4/2/1 — and of the
 * 1,166 blocks the corpus packs into, four are a single sentence of seven lines or more. The
 * tallest block anywhere is **17 line boxes** — 32 on the phone: one 1,132-character sentence
 * sitting second in a four-sentence string that draws 3/17/3/2, which `pack` never sees and
 * which no ceiling on an *opening* block would reach in any case. What the cap is measured
 * against is the complaint it was built for, and that is a different size of object: the
 * 2,139-character nineteen-sentence judgement drew **28** line boxes as one block and **54** in
 * the phone's column, and it now opens on three and five. `docs/known-defects.md` carries the
 * decision not to close this, with the reason.
 */
export const UNDER_CAP_WALL = {
  /** The candidate the judgement is about, for a failure message that names something. */
  subject: "_PROVIDERS",
  verdict: "material",
  /** Characters in the recorded string, asserted so a bad paste cannot pass silently. */
  chars: 673,
  /** Sentences the uncapped cut finds — at or under `MOST_PARTS`, which is the whole point. */
  sentences: 2,
  /** Characters per block, in order, as the shipped cut produces them. */
  blockChars: [524, 148],
  /**
   * Line boxes per block at the 617.12px measure, counted in a browser as described above. It
   * is 17 and 4 in a phone's column, which is where this entry is worth judging.
   */
  blockLines: [7, 2],
  source:
    "The detected structure (duplicated_knowledge around `_PROVIDERS` in both " +
    "`src.audiobook.preparation.providers.registry` and " +
    "`src.audiobook.synthesis.providers.registry`) costs more than it earns because the " +
    "question answers explicitly establish that 'QwenSynthesisProvider is intended to be the " +
    "sole TTS backend,' and the same constant name and pattern across these files without " +
    "separation of concerns leads to duplicated knowledge that violates the architectural rule " +
    "of maintaining a single authoritative source of truth. Therefore, the duplication costs " +
    "the team synchronized edits or divergence risk and earns nothing since there is only a " +
    "single intended TTS backend.",
} as const;
