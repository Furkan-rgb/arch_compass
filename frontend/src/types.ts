import type { components as OpenAPIComponents } from "./openapi.generated";

export type ProblemDetail = OpenAPIComponents["schemas"]["ProblemDetail"];
export type BoundaryReview = OpenAPIComponents["schemas"]["BoundaryReview"];
export type BoundaryReviewReport = OpenAPIComponents["schemas"]["BoundaryReviewReport"];
export type BoundaryReviewSummary = OpenAPIComponents["schemas"]["BoundaryReviewSummary"];
export type ReviewStatus = OpenAPIComponents["schemas"]["ReviewStatus"];
export type ReviewedBoundary = OpenAPIComponents["schemas"]["ReviewedBoundary"];
export type FindingPattern = OpenAPIComponents["schemas"]["FindingPattern"];
export type ReviewConversation = OpenAPIComponents["schemas"]["ReviewConversation"];
export type ReviewMessage = OpenAPIComponents["schemas"]["ReviewMessage"];
export type BundledExample = OpenAPIComponents["schemas"]["BundledExample"];
export type ReviewProgress = OpenAPIComponents["schemas"]["ReviewProgress"];
export type AnswerProgress = OpenAPIComponents["schemas"]["AnswerProgress"];
export type ReviewOverview = OpenAPIComponents["schemas"]["ReviewOverview"];
export type OverviewStatement = OpenAPIComponents["schemas"]["OverviewStatement"];
export type OpenQuestion = OpenAPIComponents["schemas"]["OpenQuestion"];
export type RecordedInvestigation = OpenAPIComponents["schemas"]["RecordedInvestigation"];
export type InvestigationLookup = OpenAPIComponents["schemas"]["InvestigationLookup"];
export type ArchitectureCase = OpenAPIComponents["schemas"]["ArchitectureCase"];
export type AtlasVersion = OpenAPIComponents["schemas"]["AtlasVersion"];
export type CaseRevision = OpenAPIComponents["schemas"]["CaseRevision"];
export type CaseSummary = OpenAPIComponents["schemas"]["CaseSummary"];
export type CaseUpdate = OpenAPIComponents["schemas"]["CaseUpdate"];
export type Clarification = OpenAPIComponents["schemas"]["Clarification"];
export type RecordedAnswer = OpenAPIComponents["schemas"]["RecordedAnswer"];
export type BoundaryExcerpt = OpenAPIComponents["schemas"]["BoundaryExcerpt"];
export type DirectoryListing = OpenAPIComponents["schemas"]["DirectoryListing"];

/**
 * A review as the workspace reads it: the stored document plus the one thing *now* knows
 * about it — the team's standing decisions, joined on by the server at read time and never
 * stored on the review. Where each boundary stands against the previous revision is on the
 * document itself, at `report.delta` and `report.reviewed[].delta_state`.
 */
export type ReviewDetail = OpenAPIComponents["schemas"]["ReviewDetailResponse"];
export type BoundaryTriage = OpenAPIComponents["schemas"]["BoundaryTriage"];
export type JoinedDecision = OpenAPIComponents["schemas"]["JoinedDecision"];
export type DecisionState = OpenAPIComponents["schemas"]["DecisionState"];
export type StandingDecision = OpenAPIComponents["schemas"]["StandingDecision"];
export type DecisionComment = OpenAPIComponents["schemas"]["DecisionComment"];
export type DecisionRequest = OpenAPIComponents["schemas"]["DecisionRequest"];
export type BulkDecisionRequest = OpenAPIComponents["schemas"]["BulkDecisionRequest"];
export type BulkDecisionResponse = OpenAPIComponents["schemas"]["BulkDecisionResponse"];

/**
 * What this workspace is pointed at, including being pointed at nothing.
 *
 * Aliased from the generated schema rather than restated here. It was restated, and drifted
 * the moment `reasoning` became nullable: a hand-written mirror of a contract is a second
 * copy of it that no build step checks.
 */
export type WorkspaceSummary = OpenAPIComponents["schemas"]["WorkspaceSummaryResponse"];
export type WorkspaceModels = OpenAPIComponents["schemas"]["WorkspaceModels"];
export type ModelCatalog = OpenAPIComponents["schemas"]["ModelCatalogResponse"];
export type ModelCandidate = OpenAPIComponents["schemas"]["AvailableModelResponse"];
export type ProviderAvailability =
  OpenAPIComponents["schemas"]["ProviderAvailabilityResponse"];

/** Aliased, not restated: the hand-written mirror of this one silently dropped
    `repo_id` and `branch_name` the day the server learned them. */
export type RepositorySummary = OpenAPIComponents["schemas"]["RepositorySummary"];
export type RepositoryCheckout = OpenAPIComponents["schemas"]["RepositoryCheckout"];
export type CheckoutRefresh = OpenAPIComponents["schemas"]["CheckoutRefresh"];
export type RepositoryBranch = OpenAPIComponents["schemas"]["RepositoryBranch"];
/** One folder near the top of a repository, with what excluding it would save. */
export type RepositoryFolder = OpenAPIComponents["schemas"]["RepositoryFolder"];
export type RepositoryFolderTree = OpenAPIComponents["schemas"]["RepositoryFolderTree"];

/**
 * How a review run ended, as the stream said it: with a composed review, or with the
 * workspace refusing a revision that would change nothing. Two shapes rather than a
 * nullable review, so a caller has to say which ending it is handling.
 */
export type ReviewRunOutcome =
  | { ended: "completed"; review: BoundaryReview }
  | { ended: "unchanged" };

export interface SourceLocation {
  path: string;
  start_line: number;
  end_line: number;
}

export type AtlasNodeSummary = OpenAPIComponents["schemas"]["AtlasNodeSummary"];

/** The server calls this an AtlasEdge; the page has always said "relationship". */
export type AtlasRelationship = OpenAPIComponents["schemas"]["AtlasEdge"];

export type AtlasMetricNature = "objective_measurement" | "structural_proxy";

export type AtlasMetricScope =
  | "lexical_node"
  | "owning_module"
  | "reverse_static_impact_neighbourhood"
  | "bounded_resolved_call_chain";

export type AtlasMetricValue = OpenAPIComponents["schemas"]["AtlasMetricValue"];

/** The server calls this an ObscuritySignal; the page has always said "signal". */
export type AtlasSignal = OpenAPIComponents["schemas"]["ObscuritySignal"];

export type AtlasQueryResult = OpenAPIComponents["schemas"]["AtlasQueryResult"];

export type AtlasExploreOperation =
  | "children"
  | "dependencies"
  | "dependants"
  | "callers"
  | "implementations"
  | "tests"
  | "forward_neighbourhood"
  | "reverse_neighbourhood"
  | "search"
  | "shortest_path"
  | "cycles"
  | "signals";

export type AtlasExploreRequest = OpenAPIComponents["schemas"]["AtlasExploreRequest"];

export type PolicyStrength = OpenAPIComponents["schemas"]["PolicyStrength"];
export type PolicyOrigin = OpenAPIComponents["schemas"]["PolicyOrigin"];
/** A policy as it is authored: what the form sends, and all the server accepts. */
export type PolicyDraft = OpenAPIComponents["schemas"]["PolicyDraft"];

export type Policy = OpenAPIComponents["schemas"]["PolicyDocument"];

export interface PolicyApplicability {
  user?: string | null;
  organisation?: string | null;
  repository?: string | null;
}

export type PolicySource = OpenAPIComponents["schemas"]["PolicySource"];
