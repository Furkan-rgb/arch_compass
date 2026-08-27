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
 * **What it costs.** 12,170 characters over nine strings, about 13 KB of source. `pack` is
 * O(blocks x sentences squared) — six by nineteen at the longest of these — so the whole set
 * packs in under a millisecond and the file it is read by runs in the same 70ms it did with
 * two. Nothing here is imported by the application, so none of it reaches the bundle.
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
