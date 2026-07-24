import {
  AlertCircle,
  ArrowRight,
  BookOpenText,
  Check,
  Clipboard,
  Compass,
  Download,
  FileText,
  HelpCircle,
  Layers3,
  Scale,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  RepositoryAtlas,
  type AtlasEdgeView,
  type AtlasMetricView,
  type AtlasNodeState,
  type AtlasNodeView,
} from "./atlas";
import { Badge, shortId } from "./components";
import { policyApplicabilityLabel } from "./policy-applicability";
import type {
  ArchitectureCase,
  AtlasMetricValue,
  CaseAlternative,
  Claim,
  ConsultationRun,
  RecommendationReport,
} from "./types";

export interface ArchitectureWorkspaceProps {
  architectureCase?: ArchitectureCase;
  run: ConsultationRun;
  report: RecommendationReport;
  onClaim: (claim: Claim) => void;
}

export interface WorkspaceAtlasView {
  mode: "repository" | "greenfield";
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
}

export function buildWorkspaceAtlas(
  run: ConsultationRun,
  report: RecommendationReport,
  architectureCase?: ArchitectureCase,
): WorkspaceAtlasView {
  if (!run.atlas_version_id) {
    const rootId = `decision:${architectureCase?.case_id || run.case_id}`;
    const responsibilities = report.responsibility_allocation.map((item, index) => ({
      id: `responsibility:${index}`,
      label: shortLabel(item.text),
      path: "Proposed responsibility",
      kind: "responsibility",
      state: "inference" as AtlasNodeState,
      description: item.text,
      metrics: [
        { label: "Supporting claims", value: item.supporting_claim_ids.length, group: "Evidence" },
      ],
      evidenceCount: item.supporting_claim_ids.length,
    }));
    const boundaries = report.conceptual_interfaces.map((item, index) => ({
      id: `boundary:${index}`,
      label: shortLabel(item.text),
      path: "Conceptual boundary",
      kind: "boundary",
      state: "inference" as AtlasNodeState,
      description: item.text,
      metrics: [
        { label: "Supporting claims", value: item.supporting_claim_ids.length, group: "Evidence" },
      ],
      evidenceCount: item.supporting_claim_ids.length,
    }));
    const root: AtlasNodeView = {
      id: rootId,
      label: architectureCase?.title || report.adr.title,
      path: "ArchitectureCase",
      kind: "decision",
      state: "contained",
      description: report.recommended_architecture.text,
      metrics: [
        { label: "Responsibilities", value: responsibilities.length, group: "Design" },
        { label: "Boundaries", value: boundaries.length, group: "Design" },
        { label: "Scenarios", value: report.scenario_analysis.length, group: "Validation" },
      ],
      evidenceCount: report.decision_summary.supporting_claim_ids.length,
    };
    const children = [...responsibilities, ...boundaries];
    return {
      mode: "greenfield",
      nodes: [root, ...children],
      edges: children.map((node, index) => ({
        id: `greenfield-edge:${index}`,
        sourceId: rootId,
        targetId: node.id,
        kind: node.kind === "boundary" ? "defines" : "allocates",
        confidence: .9,
      })),
    };
  }

  const nodeMap = new Map<string, AtlasNodeView>();
  const relationshipMap = new Map<string, AtlasEdgeView>();
  const evidenceCounts = new Map<string, number>();
  report.evidence_appendix.forEach((claim) =>
    claim.atlas_references.forEach((reference) =>
      evidenceCounts.set(reference.node_id, (evidenceCounts.get(reference.node_id) || 0) + 1),
    ),
  );

  for (const packet of run.focused_packets) {
    const legacyMetrics = new Map(
      packet.metrics.map((profile) => [
        profile.node_id,
        flattenMetrics(profile),
      ]),
    );
    const nodeEvidence = packet.node_evidence || [];
    const evidenceByNode = new Map(
      nodeEvidence.map((evidence) => [
        evidence.node.node_id,
        evidence,
      ]),
    );
    const summaries = new Map(
      packet.node_summaries.map((node) => [node.node_id, node]),
    );
    nodeEvidence.forEach((evidence) =>
      summaries.set(evidence.node.node_id, {
        ...evidence.node,
        summary: "",
        selection_reasons: evidence.reasons,
      }),
    );
    for (const node of summaries.values()) {
      const existing = nodeMap.get(node.node_id);
      const evidence = evidenceByNode.get(node.node_id);
      const selectionSummary = evidence?.reasons
        .map((reason) => reason.explanation)
        .join(" ");
      nodeMap.set(node.node_id, {
        id: node.node_id,
        label: node.qualified_name.split(".").at(-1) || node.qualified_name || node.path,
        path: node.location
          ? `${node.path}:${node.location.start_line}–${node.location.end_line}`
          : node.path,
        kind: node.node_type,
        state: existing?.state || "normal",
        description:
          node.summary ||
          selectionSummary ||
          packet.cluster.rationale,
        metrics:
          evidence?.metrics.map(metricView) ||
          legacyMetrics.get(node.node_id) ||
          existing?.metrics ||
          [],
        evidenceCount: evidenceCounts.get(node.node_id) || 0,
        signalCount: evidence?.signals.length || existing?.signalCount || 0,
      });
    }
    for (const relationship of packet.relationships) {
      relationshipMap.set(relationship.edge_id, {
        id: relationship.edge_id,
        sourceId: relationship.source_id,
        targetId: relationship.target_id,
        kind: relationship.edge_type,
        confidence: 1,
      });
    }
    for (const relationship of packet.relationship_evidence) {
      relationshipMap.set(relationship.edge_id, {
        id: relationship.edge_id,
        sourceId: relationship.source.node_id,
        targetId: relationship.target.node_id,
        kind: relationship.edge_type,
        confidence: relationship.confidence,
      });
    }
  }

  const nodes = [...nodeMap.values()];
  const riskScores = nodes.map((node) => ({
    id: node.id,
    score: numericMetric(node.metrics, [
      "reverse dependency reach",
      "likely affected modules",
      "cycle size",
      "local control flow complexity",
    ]),
  }));
  const maxRisk = Math.max(0, ...riskScores.map((item) => item.score));
  nodes.forEach((node) => {
    const risk = riskScores.find((item) => item.id === node.id)?.score || 0;
    node.state =
      risk > 0 && risk >= maxRisk * .72
        ? "hotspot"
        : node.kind === "repository" || node.kind === "package"
          ? "contained"
          : "normal";
  });
  const hotspotIds = new Set(nodes.filter((node) => node.state === "hotspot").map((node) => node.id));
  const edges = [...relationshipMap.values()].map((edge) => ({
    ...edge,
    risk: hotspotIds.has(edge.sourceId) && hotspotIds.has(edge.targetId),
  }));
  return { mode: "repository", nodes, edges };
}

export function ArchitectureWorkspace({
  architectureCase,
  run,
  report,
  onClaim,
}: ArchitectureWorkspaceProps) {
  const atlas = useMemo(
    () => buildWorkspaceAtlas(run, report, architectureCase),
    [architectureCase, report, run],
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    atlas.nodes[0]?.id || null,
  );
  const [activeAlternativeId, setActiveAlternativeId] = useState(
    report.alternatives_considered[0]?.id || "",
  );
  const [activeScenario, setActiveScenario] = useState(0);
  const [copied, setCopied] = useState(false);
  const claims = useMemo(
    () => uniqueClaims([
      ...report.repository_observations,
      ...report.relevant_policies,
      ...report.confirmed_context,
      ...report.assumptions_and_unresolved_questions,
    ]),
    [report],
  );
  const selectedScenario = report.scenario_analysis[activeScenario];
  const forces = run.design_forces.length ? run.design_forces : report.important_design_forces;

  const copyAdr = async () => {
    await navigator.clipboard.writeText(adrMarkdown(report));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_800);
  };

  return (
    <div className="architecture-workspace">
      <header className="workspace-header">
        <div>
          <span className="eyebrow">Architecture analysis workspace</span>
          <h2>Decision context, evidence, and recommendation</h2>
        </div>
        <div className="consultation-mode" aria-label="Consultation evidence mode">
          <span className={atlas.mode === "repository" ? "active" : ""}>
            <Layers3 size={14} /> Brownfield
          </span>
          <span className={atlas.mode === "greenfield" ? "active" : ""}>
            <Sparkles size={14} /> Greenfield
          </span>
        </div>
      </header>

      <div className="architecture-columns">
        <aside className="architecture-column architecture-column--context">
          <ArchitectureCasePanel architectureCase={architectureCase} report={report} />
          <section className="workspace-panel design-forces-panel">
            <PanelHeading eyebrow="Decision drivers" title="Design forces" icon={<Compass size={18} />} />
            <ol>
              {forces.map((force) => (
                <li key={force.force_id}>
                  <span>{force.importance}</span>
                  <strong>{force.title}</strong>
                  <p>{force.description}</p>
                </li>
              ))}
            </ol>
          </section>
        </aside>

        <div className="architecture-column architecture-column--analysis">
          <RecommendationPanel report={report} claims={claims} onClaim={onClaim} />
          <RepositoryAtlas
            title={atlas.mode === "repository" ? "RepositoryAtlas" : "Greenfield architecture canvas"}
            description={
              atlas.mode === "repository"
                ? "Only nodes surfaced in the consultation’s persisted evidence packets are shown."
                : "Responsibilities and boundaries proposed by the recommendation; these are advisor inferences, not repository facts."
            }
            mode={atlas.mode}
            nodes={atlas.nodes}
            edges={atlas.edges}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
          <AlternativesPanel
            alternatives={report.alternatives_considered}
            activeId={activeAlternativeId}
            onSelect={setActiveAlternativeId}
          />
          <ScenariosPanel
            scenarios={report.scenario_analysis}
            activeIndex={activeScenario}
            onSelect={setActiveScenario}
            activeAlternativeId={activeAlternativeId}
          />
          <AdrPanel report={report} copied={copied} onCopy={() => void copyAdr()} runId={run.run_id} />
        </div>

        <aside className="architecture-column architecture-column--evidence">
          <PoliciesPanel report={report} />
          <ClaimLedger claims={claims} onClaim={onClaim} />
          {selectedScenario && (
            <section className="workspace-panel scenario-conclusion">
              <PanelHeading eyebrow="Selected scenario" title="Conclusion" icon={<ShieldCheck size={18} />} />
              <p>{selectedScenario.conclusion}</p>
            </section>
          )}
        </aside>
      </div>

    </div>
  );
}

function ArchitectureCasePanel({
  architectureCase,
  report,
}: {
  architectureCase?: ArchitectureCase;
  report: RecommendationReport;
}) {
  const facts = architectureCase?.confirmed_facts.map((item) => item.text) ||
    report.confirmed_context.map((item) => item.text);
  const assumptions = architectureCase?.assumptions.map((item) => item.text) ||
    report.assumptions_and_unresolved_questions.map((item) => item.text);
  const questions = architectureCase?.unresolved_questions.map((item) => item.text) || [];
  const userForces = architectureCase?.design_forces.map((item) => item.text) || [];
  const advisorForces =
    architectureCase?.advisor_design_forces.map((item) => item.text) || [];
  return (
    <section className="workspace-panel architecture-case-panel">
      <PanelHeading eyebrow="Persistent context" title="ArchitectureCase" icon={<FileText size={18} />} />
      <h3>{architectureCase?.title || report.adr.title}</h3>
      <p className="architecture-case-panel__problem">
        {architectureCase?.problem_statement || report.problem_and_desired_outcome}
      </p>
      <dl>
        <div><dt>Revision</dt><dd>{architectureCase?.revision || "—"}</dd></div>
        <div><dt>Requirements</dt><dd>{architectureCase?.functional_requirements.length || facts.length}</dd></div>
        <div><dt>Future changes</dt><dd>{architectureCase?.expected_future_changes.length || report.scenario_analysis.length}</dd></div>
        <div><dt>Open questions</dt><dd>{questions.length}</dd></div>
      </dl>
      <CaseItems label="Confirmed" values={facts} icon={<Check size={12} />} />
      <CaseItems label="Assumed" values={assumptions} icon={<AlertCircle size={12} />} />
      <CaseItems label="Unresolved" values={questions} icon={<HelpCircle size={12} />} />
      <CaseItems label="User forces" values={userForces} icon={<Compass size={12} />} />
      <CaseItems
        label="Advisor forces"
        values={advisorForces}
        icon={<Sparkles size={12} />}
      />
    </section>
  );
}

function CaseItems({ label, values, icon }: { label: string; values: string[]; icon: ReactNode }) {
  const [open, setOpen] = useState(label === "Confirmed");
  if (!values.length) return null;
  return (
    <details
      className="case-items"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>{icon} {label} <span>{values.length}</span></summary>
      <ul>{values.slice(0, 6).map((value) => <li key={value}>{value}</li>)}</ul>
    </details>
  );
}

function RecommendationPanel({
  report,
  claims,
  onClaim,
}: {
  report: RecommendationReport;
  claims: Claim[];
  onClaim: (claim: Claim) => void;
}) {
  const byId = new Map(claims.map((claim) => [claim.claim_id, claim]));
  return (
    <article className="workspace-recommendation">
      <div className="workspace-recommendation__top">
        <span className="eyebrow eyebrow--light">Current recommendation</span>
        <Badge tone="teal">{report.disposition.replaceAll("_", " ")}</Badge>
      </div>
      <h2>{report.decision_summary.text}</h2>
      <p>{report.recommended_architecture.text}</p>
      <div className="workspace-recommendation__footer">
        <span>Confidence <strong>{report.confidence.level}</strong></span>
        <div className="support-links">
          {report.decision_summary.supporting_claim_ids.map((id) => (
            <button key={id} type="button" onClick={() => byId.get(id) && onClaim(byId.get(id)!)}>
              {shortId(id)}
            </button>
          ))}
        </div>
      </div>
    </article>
  );
}

function PoliciesPanel({ report }: { report: RecommendationReport }) {
  return (
    <section className="workspace-panel policies-evidence-panel">
      <PanelHeading eyebrow="Grounding" title="Relevant policies" icon={<BookOpenText size={18} />} />
      <div>
        {report.policy_evidence.map((policy) => (
          <article key={policy.id}>
            <div><Badge tone="neutral">{policy.scope}</Badge><span>{policy.strength}</span></div>
            <h3>{policy.title}</h3>
            <p>{policy.matched_sections.slice(0, 3).join(" · ") || "Policy body matched during consultation."}</p>
            <p>
              Applies to{" "}
              <strong>
                {policyApplicabilityLabel(policy.scope, policy.applies_to)}
              </strong>
            </p>
            <code>{shortId(policy.id)}</code>
          </article>
        ))}
        {!report.policy_evidence.length && <p className="muted">No policy evidence was retrieved.</p>}
      </div>
      <Link to="/policies" className="text-link">Browse policy library <ArrowRight size={13} /></Link>
    </section>
  );
}

function ClaimLedger({ claims, onClaim }: { claims: Claim[]; onClaim: (claim: Claim) => void }) {
  return (
    <section className="workspace-panel claim-ledger-panel">
      <PanelHeading eyebrow="Audit trail" title="Claim ledger" icon={<ShieldCheck size={18} />} />
      <div>
        {claims.slice(0, 12).map((claim) => (
          <button key={claim.claim_id} type="button" onClick={() => onClaim(claim)}>
            <span className={`claim-kind claim-kind--${claim.classification}`}>
              {claim.classification.replaceAll("_", " ")}
            </span>
            <p>{claim.text}</p>
            <small>{shortId(claim.claim_id)} · {claim.atlas_references.length + claim.policy_ids.length} refs</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function AlternativesPanel({
  alternatives,
  activeId,
  onSelect,
}: {
  alternatives: CaseAlternative[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="workspace-panel alternatives-panel">
      <PanelHeading eyebrow="Trade space" title="Alternatives considered" icon={<Scale size={18} />} />
      <div role="list">
        {alternatives.map((alternative) => (
          <button
            key={alternative.id}
            type="button"
            className={alternative.id === activeId ? "active" : ""}
            aria-pressed={alternative.id === activeId}
            onClick={() => onSelect(alternative.id)}
          >
            <span>{alternative.id === activeId ? <Check size={13} /> : <span />}</span>
            <strong>{alternative.title}</strong>
            <p>{alternative.summary}</p>
          </button>
        ))}
      </div>
    </section>
  );
}

function ScenariosPanel({
  scenarios,
  activeIndex,
  onSelect,
  activeAlternativeId,
}: {
  scenarios: RecommendationReport["scenario_analysis"];
  activeIndex: number;
  onSelect: (index: number) => void;
  activeAlternativeId: string;
}) {
  const scenario = scenarios[activeIndex];
  return (
    <section className="workspace-panel scenarios-panel">
      <PanelHeading eyebrow="Future change" title="Scenario analysis" icon={<Sparkles size={18} />} />
      <div className="scenario-tabs" role="tablist" aria-label="Future-change scenarios">
        {scenarios.map((item, index) => (
          <button
            key={item.scenario}
            type="button"
            role="tab"
            aria-selected={index === activeIndex}
            className={index === activeIndex ? "active" : ""}
            onClick={() => onSelect(index)}
          >
            {index + 1}. {shortLabel(item.scenario)}
          </button>
        ))}
      </div>
      {scenario && (
        <div className="scenario-detail" role="tabpanel">
          <h3>{scenario.scenario}</h3>
          {scenario.assumptions.length > 0 && (
            <p><strong>Assumes:</strong> {scenario.assumptions.join(" · ")}</p>
          )}
          <blockquote>
            {scenario.alternative_results[activeAlternativeId] ||
              Object.values(scenario.alternative_results)[0] ||
              scenario.conclusion}
          </blockquote>
          <p>{scenario.conclusion}</p>
        </div>
      )}
    </section>
  );
}

function AdrPanel({
  report,
  copied,
  onCopy,
  runId,
}: {
  report: RecommendationReport;
  copied: boolean;
  onCopy: () => void;
  runId: string;
}) {
  return (
    <section className="workspace-panel workspace-adr">
      <PanelHeading eyebrow="Decision record" title="ADR preview" icon={<FileText size={18} />} />
      <div className="workspace-adr__actions">
        <button type="button" className="button button--quiet" onClick={onCopy}>
          {copied ? <Check size={14} /> : <Clipboard size={14} />}
          {copied ? "Copied" : "Copy ADR"}
        </button>
        <a className="button button--quiet" href={`/api/runs/${runId}/report?format=markdown`}>
          <Download size={14} /> Export
        </a>
      </div>
      <Badge tone="neutral">{report.adr.status}</Badge>
      <h3>{report.adr.title}</h3>
      <p>{report.adr.context}</p>
      <strong>{report.adr.decision.text}</strong>
    </section>
  );
}

function PanelHeading({
  eyebrow,
  title,
  icon,
}: {
  eyebrow: string;
  title: string;
  icon: ReactNode;
}) {
  return (
    <div className="workspace-panel__heading">
      <div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>
      {icon}
    </div>
  );
}

function flattenMetrics(profile: {
  local: Record<string, number | string | string[] | null>;
  dependency: Record<string, number | string | string[] | null>;
  change_amplification: Record<string, number | string | string[] | null>;
  cognitive_scope: Record<string, number | string | string[] | null>;
}): AtlasMetricView[] {
  const groups = [
    ["Local", profile.local],
    ["Dependency", profile.dependency],
    ["Change", profile.change_amplification],
    ["Cognitive", profile.cognitive_scope],
  ] as const;
  return groups.flatMap(([group, values]) =>
    Object.entries(values).flatMap(([label, value]) =>
      typeof value === "number" && value > 0
        ? [{
            group,
            label: label.replaceAll("_", " "),
            value,
          }]
        : [],
    ),
  );
}

function metricView(metric: AtlasMetricValue): AtlasMetricView {
  return {
    group:
      metric.nature === "structural_proxy"
        ? "Structural proxy"
        : "Objective measurement",
    label: metric.metric.replaceAll("_", " ").replaceAll(".", " · "),
    value: metric.value,
    nature: metric.nature,
    scope: metric.scope,
    definition: metric.definition,
    limitations: metric.limitations,
  };
}

function numericMetric(metrics: AtlasMetricView[], labels: string[]) {
  return metrics
    .filter(
      (metric) =>
        labels.some(
          (label) =>
            metric.label === label || metric.label.endsWith(` · ${label}`),
        ) && typeof metric.value === "number",
    )
    .reduce((sum, metric) => sum + Number(metric.value), 0);
}

function uniqueClaims(claims: Claim[]) {
  return [...new Map(claims.map((claim) => [claim.claim_id, claim])).values()];
}

function shortLabel(value: string) {
  const first = value.split(/[.!?]\s/)[0].trim();
  return first.length > 48 ? `${first.slice(0, 47)}…` : first;
}

function adrMarkdown(report: RecommendationReport) {
  return [
    `# ${report.adr.title}`,
    "",
    `Status: ${report.adr.status}`,
    "",
    "## Context",
    "",
    report.adr.context,
    "",
    "## Decision",
    "",
    report.adr.decision.text,
    "",
    "## Consequences",
    "",
    ...report.adr.consequences.map((item) => `- ${item.text}`),
  ].join("\n");
}
