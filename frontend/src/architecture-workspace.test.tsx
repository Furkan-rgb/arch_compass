import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { ArchitectureWorkspace, buildWorkspaceAtlas } from "./architecture-workspace";
import { layoutAtlas, RepositoryAtlas, type AtlasNodeView } from "./atlas";
import type {
  ArchitectureCase,
  ConsultationRun,
  RecommendationReport,
} from "./types";

const statement = (text: string, supporting_claim_ids = ["claim_repo"]) => ({
  text,
  classification: "advisor_inference" as const,
  supporting_claim_ids,
});

const report: RecommendationReport = {
  report_id: "report_1",
  disposition: "move_responsibility",
  decision_summary: statement("Move provider discovery behind the provider boundary."),
  problem_and_desired_outcome: "Provider behavior leaks across composition and workflow.",
  confirmed_context: [],
  assumptions_and_unresolved_questions: [],
  important_design_forces: [{
    force_id: "force_1",
    title: "One owner",
    description: "Provider knowledge needs one accountable owner.",
    importance: "high",
  }],
  repository_observations: [{
    claim_id: "claim_repo",
    text: "ServiceA calls ServiceB directly.",
    classification: "repository_observation",
    atlas_references: [{ node_id: "node_a", location: { path: "a.py", start_line: 1, end_line: 8 } }],
    policy_ids: [],
  }],
  relevant_policies: [],
  policy_evidence: [{
    id: "policy_1",
    title: "Place knowledge with its owner",
    scope: "general",
    strength: "guidance",
    matched_sections: ["Responsibility"],
  }],
  recommended_architecture: statement("Provider owns discovery and exposes a narrow query."),
  responsibility_allocation: [statement("Provider owns built-in voice discovery.")],
  conceptual_interfaces: [statement("Expose a provider capability query.")],
  alternatives_considered: [
    { id: "alt_a", title: "Keep leakage", summary: "Leave behavior distributed." },
    { id: "alt_b", title: "Move ownership", summary: "Centralize provider knowledge." },
  ],
  scenario_analysis: [
    {
      scenario: "Add a second provider",
      assumptions: ["The provider has different voices."],
      alternative_results: { alt_a: "Requires coordinated edits.", alt_b: "Adds one implementation." },
      conclusion: "Moving ownership limits change amplification.",
    },
    {
      scenario: "Remove built-in voices",
      assumptions: [],
      alternative_results: { alt_a: "Leaks remain.", alt_b: "One owner changes." },
      conclusion: "The boundary remains useful.",
    },
  ],
  change_amplification_analysis: statement("One owner reduces coordinated edits."),
  trade_offs: [statement("Adds one provider capability method.")],
  implementation_sequence: [statement("Move discovery into the provider.")],
  confidence: { level: "high", rationale: "Repository and policy evidence agree." },
  reversal_conditions: [statement("Revisit if discovery becomes global.")],
  revisit_triggers: [statement("A provider cannot own discovery.")],
  adr: {
    title: "Centralize provider discovery",
    status: "proposed",
    context: "Provider voice knowledge is distributed.",
    decision: statement("Move voice discovery into the provider."),
    consequences: [statement("Callers no longer know built-in voice names.")],
  },
  evidence_appendix: [],
};

const brownfieldRun = {
  run_id: "run_1",
  status: "succeeded",
  case_id: "case_1",
  input_case_revision: 1,
  result_case_revision: 2,
  atlas_version_id: "atlas_1",
  policy_index_version_id: "policy_index_1",
  reasoning_model: "reasoning",
  embedding_model: "embedding",
  design_forces: report.important_design_forces,
  clusters: [],
  query_plans: [],
  focused_packets: [{
    cluster: {
      cluster_id: "cluster_1",
      title: "Provider ownership",
      rationale: "Locate distributed provider knowledge.",
    },
    node_summaries: [
      { node_id: "node_a", path: "a.py", qualified_name: "ServiceA", node_type: "class", summary: "Caller." },
      { node_id: "node_b", path: "b.py", qualified_name: "ServiceB", node_type: "class", summary: "Provider." },
    ],
    metrics: [{
      node_id: "node_a",
      local: { branch_count: 2 },
      dependency: { reverse_dependency_reach: 9 },
      change_amplification: { likely_affected_modules: 4 },
      cognitive_scope: { local_control_flow_complexity: 2 },
    }],
    relationships: [{
      edge_id: "edge_1",
      source_id: "node_a",
      target_id: "node_b",
      edge_type: "calls",
    }],
    excerpts: [],
    policies: [],
  }],
  concern_analyses: [],
  alternatives: report.alternatives_considered,
  scenarios: report.scenario_analysis,
  report,
  markdown_report: "# Report",
  initial_validation_errors: [],
  repair_actions: [],
  final_validation_errors: [],
  stage_timings: {},
  sanitized_errors: [],
  started_at: "2026-01-01T00:00:00Z",
  completed_at: "2026-01-01T00:00:01Z",
  execution_metadata: {},
} as ConsultationRun;

const architectureCase = {
  case_id: "case_1",
  revision: 2,
  title: "Provider ownership",
  problem_statement: "Provider knowledge leaks across callers.",
  desired_outcome: "One owner.",
  actors_and_workflows: [],
  functional_requirements: ["Discover voices"],
  quality_attributes: [],
  technical_constraints: [],
  organisational_constraints: [],
  expected_future_changes: ["Add provider"],
  non_goals: [],
  confirmed_facts: [{ id: "fact_1", text: "A provider exists.", kind: "fact" }],
  derived_constraints: [],
  assumptions: [],
  unresolved_questions: [],
  design_forces: [],
  repository: { root_path: "/project", atlas_version_id: "atlas_1" },
  referenced_policy_ids: [],
  candidate_alternatives: [],
  reversal_conditions: [],
  revisit_triggers: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:01Z",
} as ArchitectureCase;

describe("RepositoryAtlas", () => {
  it("places connected hierarchy levels and homogeneous topology logically", () => {
    const hierarchy: AtlasNodeView[] = [
      { id: "repo", label: "Repository", path: ".", kind: "repository", state: "contained", metrics: [] },
      { id: "module_a", label: "ModuleA", path: "a.py", kind: "module", state: "normal", metrics: [] },
      { id: "module_b", label: "ModuleB", path: "b.py", kind: "module", state: "normal", metrics: [] },
      { id: "class_a", label: "ClassA", path: "a.py", kind: "class", state: "normal", metrics: [] },
      { id: "class_b", label: "ClassB", path: "b.py", kind: "class", state: "normal", metrics: [] },
    ];
    const layout = layoutAtlas(hierarchy, [
      { id: "r-a", sourceId: "repo", targetId: "module_a", kind: "contains" },
      { id: "r-b", sourceId: "repo", targetId: "module_b", kind: "contains" },
      { id: "a-c", sourceId: "module_a", targetId: "class_a", kind: "contains" },
      { id: "b-c", sourceId: "module_b", targetId: "class_b", kind: "contains" },
    ]);

    expect(layout.positions.get("repo")!.y).toBeLessThan(layout.positions.get("module_a")!.y);
    expect(layout.positions.get("module_a")!.y).toBeLessThan(layout.positions.get("class_a")!.y);
    expect(
      Math.abs(layout.positions.get("module_a")!.x - layout.positions.get("class_a")!.x),
    ).toBeLessThan(
      Math.abs(layout.positions.get("module_b")!.x - layout.positions.get("class_a")!.x),
    );

    const homogeneous = layoutAtlas(
      ["a", "b", "c"].map((id) => ({
        id,
        label: id,
        path: `${id}.py`,
        kind: "class",
        state: "normal",
        metrics: [],
      })),
      [
        { id: "a-b", sourceId: "a", targetId: "b", kind: "calls" },
        { id: "b-c", sourceId: "b", targetId: "c", kind: "calls" },
      ],
    );
    expect(homogeneous.positions.get("b")!.y).toBeLessThan(homogeneous.positions.get("a")!.y);
    expect(homogeneous.positions.get("b")!.y).toBeLessThan(homogeneous.positions.get("c")!.y);
  });

  it("lets keyboard users select a node and updates its detail panel", () => {
    const nodes: AtlasNodeView[] = [
      { id: "a", label: "ServiceA", path: "a.py", kind: "class", state: "normal", metrics: [] },
      { id: "b", label: "ServiceB", path: "b.py", kind: "class", state: "hotspot", metrics: [] },
    ];
    function Harness() {
      const [selected, setSelected] = useState("a");
      return (
        <RepositoryAtlas
          nodes={nodes}
          edges={[{ id: "edge", sourceId: "a", targetId: "b", kind: "calls" }]}
          selectedNodeId={selected}
          onSelectNode={setSelected}
        />
      );
    }
    render(<Harness />);

    fireEvent.keyDown(screen.getByRole("treeitem", { name: "ServiceB, class, hotspot" }), {
      key: "Enter",
    });
    expect(screen.getByRole("heading", { name: "ServiceB" })).toBeVisible();
    expect(screen.getByText("b.py")).toBeVisible();
  });

  it("provides zoom, fit, scrolling, and drag-panning controls", () => {
    const nodes: AtlasNodeView[] = [
      { id: "a", label: "ServiceA", path: "a.py", kind: "class", state: "normal", metrics: [] },
      { id: "b", label: "ServiceB", path: "b.py", kind: "class", state: "normal", metrics: [] },
    ];
    render(
      <RepositoryAtlas
        nodes={nodes}
        edges={[{ id: "edge", sourceId: "a", targetId: "b", kind: "calls" }]}
        selectedNodeId="a"
        onSelectNode={vi.fn()}
      />,
    );

    expect(screen.getByRole("region", { name: "Scrollable graph viewport" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByRole("status", { name: "Current graph zoom" })).toHaveTextContent("115%");
    expect(screen.getByRole("button", { name: "Fit graph to view" })).toBeEnabled();

    const viewport = screen.getByRole("region", { name: "Scrollable graph viewport" });
    fireEvent.pointerDown(viewport, { button: 0, pointerId: 1, clientX: 120, clientY: 90 });
    expect(viewport).toHaveClass("atlas-canvas--panning");
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 70, clientY: 50 });
    fireEvent.pointerUp(viewport, { pointerId: 1, clientX: 70, clientY: 50 });
    expect(viewport).not.toHaveClass("atlas-canvas--panning");
  });
});

describe("architecture workspace", () => {
  it("uses persisted packets for brownfield and derives a separate greenfield canvas", () => {
    expect(buildWorkspaceAtlas(brownfieldRun, report, architectureCase)).toMatchObject({
      mode: "repository",
      nodes: expect.arrayContaining([expect.objectContaining({ id: "node_a", state: "hotspot" })]),
      edges: [expect.objectContaining({ sourceId: "node_a", targetId: "node_b" })],
    });

    const greenfield = buildWorkspaceAtlas(
      { ...brownfieldRun, atlas_version_id: null, focused_packets: [] },
      report,
      { ...architectureCase, repository: null },
    );
    expect(greenfield.mode).toBe("greenfield");
    expect(greenfield.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "responsibility", state: "inference" }),
        expect.objectContaining({ kind: "boundary", state: "inference" }),
      ]),
    );
  });

  it("synchronizes alternatives and scenarios, copies the ADR, and continues the case", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const onContinue = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <ArchitectureWorkspace
          architectureCase={architectureCase}
          run={brownfieldRun}
          report={report}
          onClaim={vi.fn()}
          onContinue={onContinue}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Move ownership/ }));
    fireEvent.click(screen.getByRole("tab", { name: /Remove built-in voices/ }));
    expect(screen.getByText("One owner changes.")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Copy ADR" }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining("# Centralize provider discovery")),
    );
    expect(screen.getByRole("button", { name: "Copied" })).toBeVisible();

    fireEvent.change(screen.getByPlaceholderText(/Add a new constraint/), {
      target: { value: "What if discovery becomes remote?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Consult again" }));
    await waitFor(() =>
      expect(onContinue).toHaveBeenCalledWith("What if discovery becomes remote?"),
    );
  });
});
