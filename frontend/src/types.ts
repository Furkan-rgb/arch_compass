import type { components as OpenAPIComponents } from "./openapi.generated";

export type ProblemDetail = OpenAPIComponents["schemas"]["ProblemDetail"];
export type BoundaryReview = OpenAPIComponents["schemas"]["BoundaryReview"];
export type BoundaryReviewReport = OpenAPIComponents["schemas"]["BoundaryReviewReport"];
export type BoundaryReviewSummary = OpenAPIComponents["schemas"]["BoundaryReviewSummary"];
export type ReviewedBoundary = OpenAPIComponents["schemas"]["ReviewedBoundary"];
export type ReviewConversation = OpenAPIComponents["schemas"]["ReviewConversation"];
export type ReviewMessage = OpenAPIComponents["schemas"]["ReviewMessage"];
export type BundledCase = OpenAPIComponents["schemas"]["BundledCase"];
export type ReviewScore = OpenAPIComponents["schemas"]["ReviewScoreResponse"];

export interface WorkspaceSummary {
  workspace: string;
  models: {
    reasoning: { provider: string; model: string };
    embedding: { provider: string; model: string; dimensions: number };
  };
  policy_index: Record<string, unknown> | null;
}

export interface RecommendationState {
  summary: string;
  rationale: string;
  run_id?: string | null;
  disposition?: string | null;
}

export interface Confidence {
  level: "low" | "medium" | "high";
  rationale: string;
}

export interface CaseSummary {
  case_id: string;
  revision: number;
  title: string;
  problem_statement: string;
  repository_root?: string | null;
  current_recommendation?: RecommendationState | null;
  confidence?: Confidence | null;
  updated_at: string;
}

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

export interface AtlasSelectionReason {
  kind:
    | "overview"
    | "metric_rank"
    | "name_match"
    | "relation"
    | "neighbourhood"
    | "path"
    | "cycle"
    | "excerpt"
    | "explicit_details";
  explanation: string;
  metric?: string | null;
  related_node_id?: string | null;
}

export interface AtlasNodeEvidence {
  node: AtlasNodeSummary;
  reasons: AtlasSelectionReason[];
  metrics: AtlasMetricValue[];
  signals: AtlasSignal[];
}

export interface AtlasRelationshipEvidence {
  edge_id: string;
  edge_type: string;
  source: AtlasNodeSummary;
  target: AtlasNodeSummary;
  confidence: number;
  location?: SourceLocation | null;
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

export interface RunSummary {
  run_id: string;
  case_id: string;
  status: "succeeded" | "failed";
  input_case_revision: number;
  result_case_revision?: number | null;
  disposition?: string | null;
  failure_stage?: string | null;
  started_at: string;
  completed_at: string;
}

export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "succeeded_with_warnings"
  | "failed"
  | "interrupted";

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

export interface ConsultationJob {
  run_id: string;
  case_id: string;
  input_case_revision: number;
  repository_root?: string | null;
  status: JobStatus;
  current_stage?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  warning?: string | null;
  error?: string | null;
  failure_diagnostics: FailureDiagnostic[];
}

export interface ProgressEvent {
  run_id: string;
  sequence: number;
  event_type:
    | "queued"
    | "stage_started"
    | "artifact_available"
    | "stage_completed"
    | "warning"
    | "completed"
    | "failed";
  stage?: string | null;
  title: string;
  summary: string;
  data: Record<string, unknown>;
  occurred_at: string;
}

export interface Claim {
  claim_id: string;
  text: string;
  classification: string;
  atlas_references: Array<{
    node_id: string;
    location?: { path: string; start_line: number; end_line: number } | null;
  }>;
  policy_ids: string[];
}

export interface SupportedStatement {
  text: string;
  classification: string;
  supporting_claim_ids: string[];
}

export interface FocusedAnalysisPacket {
  cluster: {
    cluster_id: string;
    title: string;
    rationale: string;
    design_force_ids: string[];
  };
  node_summaries: Array<{
    node_id: string;
    path: string;
    qualified_name: string;
    node_type: string;
    location?: { path: string; start_line: number; end_line: number } | null;
    summary: string;
    selection_reasons: AtlasSelectionReason[];
  }>;
  node_evidence: AtlasNodeEvidence[];
  metrics: Array<{
    node_id: string;
    local: Record<string, number | string | string[] | null>;
    dependency: Record<string, number | string | string[] | null>;
    change_amplification: Record<string, number | string | string[] | null>;
    cognitive_scope: Record<string, number | string | string[] | null>;
  }>;
  relationships: AtlasRelationship[];
  relationship_evidence: AtlasRelationshipEvidence[];
  test_ids: string[];
  test_evidence: AtlasNodeSummary[];
  excerpts: Array<{
    node_id: string;
    location: { path: string; start_line: number; end_line: number };
    text: string;
  }>;
  policies: Array<{
    policy: Policy;
    chunks: Array<{
      chunk_id: string;
      policy_id: string;
      section: string;
      ordinal: number;
      text: string;
    }>;
    distance: number;
  }>;
  assumptions: string[];
  uncertainty: string[];
}

export interface CaseStatement {
  id: string;
  text: string;
  kind: "fact" | "derived_constraint" | "assumption" | "question" | "force";
  source?: string | null;
}

export interface ArchitectureCase {
  case_id: string;
  revision: number;
  title: string;
  problem_statement: string;
  desired_outcome: string;
  actors_and_workflows: string[];
  functional_requirements: string[];
  quality_attributes: string[];
  technical_constraints: string[];
  organisational_constraints: string[];
  expected_future_changes: string[];
  non_goals: string[];
  confirmed_facts: CaseStatement[];
  derived_constraints: CaseStatement[];
  assumptions: CaseStatement[];
  unresolved_questions: CaseStatement[];
  design_forces: CaseStatement[];
  advisor_design_forces: CaseStatement[];
  repository?: {
    root_path: string;
    atlas_version_id?: string | null;
  } | null;
  policy_applicability: PolicyApplicability;
  referenced_policy_ids: string[];
  candidate_alternatives: Array<{ id: string; title: string; summary: string }>;
  current_recommendation?: RecommendationState | null;
  confidence?: Confidence | null;
  reversal_conditions: string[];
  revisit_triggers: string[];
  created_at: string;
  updated_at: string;
}

export interface CaseRevision {
  case_id: string;
  revision: number;
  snapshot: ArchitectureCase;
  event_type: "created" | "user_update" | "consultation";
  actor: string;
  created_at: string;
  origin_run_id?: string | null;
}

export interface DesignForce {
  force_id: string;
  title: string;
  description: string;
  importance: "low" | "medium" | "high" | "critical";
  importance_rationale: string;
}

export interface ConcernCluster {
  cluster_id: string;
  title: string;
  rationale: string;
  design_force_ids: string[];
}

export interface CaseAlternative {
  id: string;
  title: string;
  summary: string;
}

export interface ScenarioEvaluation {
  scenario: string;
  assumptions: string[];
  alternative_results: Record<string, string>;
  conclusion: string;
}

export interface ArchitecturalFinding {
  finding_id: string;
  title: string;
  summary: string;
  concern_cluster_id?: string | null;
  importance: "low" | "medium" | "high" | "critical";
  importance_rationale: string;
  confidence: Confidence;
  consequence: string;
  claim_ids: string[];
  atlas_node_ids: string[];
  policy_ids: string[];
  affected_locations: AtlasNodeSummary[];
  metric_observations: AtlasMetricValue[];
  obscurity_signals: AtlasSignal[];
  recommended_response: string;
  uncertainty: string[];
}

export interface RecommendationReport {
  schema_version: 3;
  report_id: string;
  disposition: string;
  decision_summary: SupportedStatement;
  problem_and_desired_outcome: string;
  confirmed_context: Claim[];
  assumptions_and_unresolved_questions: Claim[];
  important_design_forces: DesignForce[];
  findings: ArchitecturalFinding[];
  repository_observations: Claim[];
  relevant_policies: Claim[];
  policy_evidence: Array<{
    id: string;
    title: string;
    scope: string;
    applies_to: string | null;
    strength: string;
    matched_sections: string[];
  }>;
  recommended_architecture: SupportedStatement;
  responsibility_allocation: SupportedStatement[];
  conceptual_interfaces: SupportedStatement[];
  alternatives_considered: Array<{ id: string; title: string; summary: string }>;
  scenario_analysis: Array<{
    scenario: string;
    assumptions: string[];
    alternative_results: Record<string, string>;
    conclusion: string;
  }>;
  change_amplification_analysis: SupportedStatement;
  trade_offs: SupportedStatement[];
  implementation_sequence: SupportedStatement[];
  confidence: Confidence;
  reversal_conditions: SupportedStatement[];
  revisit_triggers: SupportedStatement[];
  adr: {
    title: string;
    status: string;
    context: string;
    decision: SupportedStatement;
    consequences: SupportedStatement[];
  };
  evidence_appendix: Claim[];
}

export interface ConsultationRun {
  schema_version: 3;
  run_id: string;
  status: "succeeded" | "failed";
  case_id: string;
  input_case_revision: number;
  result_case_revision?: number | null;
  atlas_version_id?: string | null;
  policy_index_version_id?: string | null;
  reasoning_model: string;
  embedding_model: string;
  design_forces: DesignForce[];
  clusters: ConcernCluster[];
  query_plans: unknown[];
  focused_packets: FocusedAnalysisPacket[];
  concern_analyses: unknown[];
  alternatives: CaseAlternative[];
  scenarios: ScenarioEvaluation[];
  report?: RecommendationReport | null;
  markdown_report?: string | null;
  initial_validation_errors: string[];
  repair_actions: string[];
  final_validation_errors: string[];
  stage_timings: Record<string, number>;
  failure_stage?: string | null;
  sanitized_errors: string[];
  failure_diagnostics: FailureDiagnostic[];
  started_at: string;
  completed_at: string;
  execution_metadata: Record<string, unknown>;
}

export interface Policy {
  id: string;
  title: string;
  scope: string;
  applies_to: string | null;
  strength: string;
  tags: string[];
  source: { author: string; inspiration: string[] };
  body: string;
  source_path: string;
  content_hash: string;
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

export interface ArchitectureCaseInput {
  title: string;
  problem_statement: string;
  desired_outcome: string;
  actors_and_workflows: string[];
  functional_requirements: string[];
  quality_attributes: string[];
  technical_constraints: string[];
  organisational_constraints: string[];
  expected_future_changes: string[];
  non_goals: string[];
  confirmed_facts: Array<{ text: string; kind: "fact" }>;
  design_forces?: Array<{ text: string; kind: "force"; source?: string | null }>;
  policy_applicability?: PolicyApplicability;
}

export interface ArchitectureCaseUpdate {
  unresolved_questions?: Array<Omit<CaseStatement, "id"> & { id?: string }>;
  design_forces?: Array<Omit<CaseStatement, "id"> & { id?: string }>;
  policy_applicability?: PolicyApplicability;
}
