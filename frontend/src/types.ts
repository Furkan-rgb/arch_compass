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
 * A review as the workspace reads it: the stored document plus what *now* knows about it —
 * each boundary's standing against its branch's baseline, and the team's decisions. Both
 * are joined on by the server at read time and never stored on the review.
 */
export type ReviewDetail = OpenAPIComponents["schemas"]["ReviewDetailResponse"];
export type ReviewedBoundaryDetail =
  OpenAPIComponents["schemas"]["ReviewedBoundaryDetail"];
export type BoundaryTriage = OpenAPIComponents["schemas"]["BoundaryTriage"];
export type JoinedDecision = OpenAPIComponents["schemas"]["JoinedDecision"];
export type DecisionState = OpenAPIComponents["schemas"]["DecisionState"];
export type StandingDecision = OpenAPIComponents["schemas"]["StandingDecision"];
export type DecisionComment = OpenAPIComponents["schemas"]["DecisionComment"];
export type DecisionRequest = OpenAPIComponents["schemas"]["DecisionRequest"];
export type BaselineSummary = OpenAPIComponents["schemas"]["BaselineSummary"];
export type BaselineOutcome = OpenAPIComponents["schemas"]["BaselineOutcome"];
export type BoundaryDispositionKind =
  OpenAPIComponents["schemas"]["BoundaryDisposition"];

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

export interface RepositorySummary {
  version_id: string;
  repository_identity: string;
  root_path: string;
  git_commit_sha?: string | null;
  created_at: string;
  node_count: number;
  edge_count: number;
  signal_count: number;
}

export interface SourceLocation {
  path: string;
  start_line: number;
  end_line: number;
}

export interface AtlasNodeSummary {
  node_id: string;
  qualified_name: string;
  node_type: string;
  path: string;
  location?: SourceLocation | null;
  is_public?: boolean | null;
}

export interface AtlasRelationship {
  edge_id: string;
  source_id: string;
  target_id: string;
  edge_type: string;
  confidence: number;
  location?: SourceLocation | null;
}

export type AtlasMetricNature = "objective_measurement" | "structural_proxy";

export type AtlasMetricScope =
  | "lexical_node"
  | "owning_module"
  | "reverse_static_impact_neighbourhood"
  | "bounded_resolved_call_chain";

export interface AtlasMetricValue {
  node_id: string;
  metric: string;
  value: number;
  rank?: number | null;
  nature: AtlasMetricNature;
  scope: AtlasMetricScope;
  definition: string;
  limitations: string;
}

export interface AtlasSignal {
  code: string;
  message: string;
  node_id: string;
  location?: SourceLocation | null;
  nature: AtlasMetricNature;
  definition: string;
  limitations: string;
}

export interface AtlasQueryResult {
  query: Record<string, unknown>;
  node_ids: string[];
  summary: string;
  node_summaries: AtlasNodeSummary[];
  metric_values: AtlasMetricValue[];
  relationships: AtlasRelationship[];
  test_ids: string[];
  signals: AtlasSignal[];
  excerpts: Array<{
    node_id: string;
    location: SourceLocation;
    text: string;
  }>;
}

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

export interface AtlasExploreRequest {
  root_path: string;
  operation: AtlasExploreOperation;
  node_id?: string;
  target_id?: string;
  terms?: string[];
  signal_codes?: string[];
  depth?: number;
  limit?: number;
}

export type FailureDiagnosticCode =
  | "cluster_count_out_of_range"
  | "unknown_force_references"
  | "missing_force_references"
  | "duplicate_force_references"
  | "duplicate_cluster_ids";

export interface FailureDiagnostic {
  code: FailureDiagnosticCode;
  force_handles: string[];
  count?: number | null;
}

export type PolicyStrength = OpenAPIComponents["schemas"]["PolicyStrength"];
export type PolicyOrigin = OpenAPIComponents["schemas"]["PolicyOrigin"];
/** A policy as it is authored: what the form sends, and all the server accepts. */
export type PolicyDraft = OpenAPIComponents["schemas"]["PolicyDraft"];

export interface Policy {
  id: string;
  title: string;
  /** The authored précis. Optional: policies from outside sources may not carry one. */
  description?: string | null;
  scope: string;
  applies_to: string | null;
  strength: string;
  tags: string[];
  source: { author: string; inspiration: string[] };
  body: string;
  source_path: string;
  content_hash: string;
  /**
   * Whose file this is, and so whether this workspace may rewrite it.
   *
   * Read from the server and never worked out here. Which directory a policy came from is a
   * fact the workspace holds — a page that guessed it from `source_path` would offer an edit
   * the server then refuses, or worse, hide one it would have allowed.
   */
  origin?: PolicyOrigin;
}

export interface PolicyApplicability {
  user?: string | null;
  organisation?: string | null;
  repository?: string | null;
}

export interface PolicySource {
  canonical_path: string;
  registered_at: string;
}
