import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BookOpenText,
  Check,
  ChevronRight,
  Circle,
  CircleCheck,
  Clock3,
  Code2,
  Compass,
  FileCode2,
  FileText,
  Lightbulb,
  Network,
  RefreshCcw,
  Scale,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import { ArchitectureWorkspace } from "../architecture-workspace";
import {
  Badge,
  ErrorPanel,
  Loading,
  PageHeader,
  Stat,
  formatDate,
  shortId,
  useDialogFocus,
} from "../components";
import { FailureDiagnostics } from "../failure-diagnostics";
import { policyApplicabilityLabel } from "../policy-applicability";
import type {
  Claim,
  ConsultationRun,
  FocusedAnalysisPacket,
  JobStatus,
  ProgressEvent,
  RecommendationReport,
} from "../types";

const stageGroups = [
  { label: "Prepare context", stages: ["atlas_resolution", "policy"], icon: Compass },
  { label: "Discover forces", stages: ["design_forces", "clustering"], icon: Lightbulb },
  { label: "Inspect code", stages: ["query_planning", "query_execution"], icon: Code2 },
  { label: "Apply policies", stages: ["policy_retrieval", "concern_analysis"], icon: ShieldCheck },
  { label: "Compare options", stages: ["alternatives", "scenarios"], icon: Scale },
  { label: "Recommend", stages: ["synthesis"], icon: Sparkles },
  { label: "Validate", stages: ["validation", "rendering"], icon: CircleCheck },
  { label: "Save report", stages: ["commit", "report_writing"], icon: FileText },
];

const eventNames = [
  "queued",
  "stage_started",
  "artifact_available",
  "stage_completed",
  "warning",
  "completed",
  "failed",
];

type Tab = "recommendation" | "report" | "trace" | "evidence" | "details";

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("recommendation");
  const [selectedClaim, setSelectedClaim] = useState<Claim | null>(null);
  const [showRevision, setShowRevision] = useState(false);
  const [revisionPrompt, setRevisionPrompt] = useState("");
  const job = useQuery({
    queryKey: ["job", runId],
    queryFn: () => api.job(runId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data && ["queued", "running"].includes(query.state.data.status)
        ? 1_500
        : false,
  });
  const events = useQuery({
    queryKey: ["events", runId],
    queryFn: () => api.events(runId),
    enabled: Boolean(job.data),
    retry: false,
  });
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    retry: false,
    refetchInterval: (query) => (!query.state.data && job.data ? 1_500 : false),
  });
  const caseId = run.data?.case_id || job.data?.case_id || "";
  const architectureCase = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.case(caseId),
    enabled: Boolean(caseId),
  });
  const reviseConsultation = useMutation({
    mutationFn: async (question: string) => {
      if (!architectureCase.data) {
        throw new Error("The ArchitectureCase is not available yet.");
      }
      const revision = await api.updateCase(architectureCase.data.case_id, {
        unresolved_questions: [
          ...architectureCase.data.snapshot.unresolved_questions,
          { text: question, kind: "question", source: "case_revision" },
        ],
      });
      return api.startConsultation(
        revision.case_id,
        architectureCase.data.snapshot.repository?.root_path ||
          job.data?.repository_root ||
          undefined,
      );
    },
    onSuccess: (nextJob) => navigate(`/runs/${nextJob.run_id}`),
  });

  useEffect(() => {
    if (!job.data || !["queued", "running"].includes(job.data.status)) return;
    const source = new EventSource(`/api/consultations/${runId}/stream`);
    const update = () => {
      void queryClient.invalidateQueries({ queryKey: ["events", runId] });
      void queryClient.invalidateQueries({ queryKey: ["job", runId] });
      void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
    };
    eventNames.forEach((name) => source.addEventListener(name, update));
    source.onerror = update;
    return () => source.close();
  }, [job.data?.status, queryClient, runId]);

  if (!job.data && !run.data && (job.isLoading || run.isLoading)) {
    return <Loading label="Opening consultation trail…" />;
  }
  if (!job.data && !run.data && job.error && run.error) {
    return <ErrorPanel error={run.error} />;
  }

  const status = job.data?.status || run.data?.status || "running";
  const report = run.data?.report || null;
  const active = ["queued", "running"].includes(status);
  const failed = ["failed", "interrupted"].includes(status);
  const failureDiagnostics = job.data?.failure_diagnostics?.length
    ? job.data.failure_diagnostics
    : run.data?.failure_diagnostics || [];
  const submitRevision = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = revisionPrompt.trim();
    if (!value || reviseConsultation.isPending) return;
    reviseConsultation.mutate(value);
  };

  return (
    <div className="page">
      <Link to="/runs" className="back-link"><ArrowLeft size={15} /> All runs</Link>
      <PageHeader
        eyebrow={active ? "Consultation in progress" : failed ? "Consultation stopped" : "Recommendation report"}
        title={
          report?.adr.title ||
          [...(events.data || [])]
            .reverse()
            .find((event) => event.event_type === "artifact_available")?.title ||
          "Following the Compass Trail"
        }
        description={
          report?.decision_summary.text ||
          job.data?.error ||
          "Arch Compass is moving from bounded context to an evidence-checked recommendation."
        }
        action={
          <div className="run-header-actions">
            <Badge tone={active ? "teal" : failed ? "danger" : "success"}>
              {active && <span className="badge-pulse" />}
              {status.replaceAll("_", " ")}
            </Badge>
            {report && (
              <button
                type="button"
                className="button button--secondary"
                onClick={() => setShowRevision((value) => !value)}
                aria-expanded={showRevision}
              >
                <RefreshCcw size={15} /> Revise case &amp; run again
              </button>
            )}
          </div>
        }
      />

      <section className="run-overview">
        <div>
          <span>Run</span>
          <strong title={runId}>{shortId(runId)}</strong>
        </div>
        <div>
          <span>Case revision</span>
          <strong>{run.data?.input_case_revision || job.data?.input_case_revision}</strong>
        </div>
        <div>
          <span>Elapsed</span>
          <strong>
            <ElapsedTime
              active={active}
              start={run.data?.started_at || job.data?.started_at}
              end={run.data?.completed_at || job.data?.completed_at}
            />
          </strong>
        </div>
        <div>
          <span>Disposition</span>
          <strong>{report?.disposition.replaceAll("_", " ") || "Pending"}</strong>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{report?.confidence.level || "Pending"}</strong>
        </div>
      </section>

      {showRevision && report && (
        <form className="revision-run-panel" onSubmit={submitRevision}>
          <div>
            <span className="eyebrow">New analysis</span>
            <h2>Revise the ArchitectureCase</h2>
            <p>
              Use this only when a premise, constraint, requirement, or scenario has changed.
              Arch Compass will create a new immutable case revision and perform a complete run.
            </p>
          </div>
          <label>
            <span>What changed?</span>
            <textarea
              rows={3}
              value={revisionPrompt}
              onChange={(event) => setRevisionPrompt(event.target.value)}
              placeholder="A hosted provider is now committed for the next release…"
              autoFocus
            />
          </label>
          <div className="revision-run-panel__actions">
            <button
              type="button"
              className="button button--quiet"
              onClick={() => {
                setShowRevision(false);
                setRevisionPrompt("");
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="button button--primary"
              disabled={!revisionPrompt.trim() || reviseConsultation.isPending}
            >
              <RefreshCcw size={15} />
              {reviseConsultation.isPending ? "Starting new run…" : "Create revision and run"}
            </button>
          </div>
        </form>
      )}

      {job.data?.warning && (
        <div className="notice notice--warning">
          <AlertTriangle size={19} />
          <div><strong>Completed with a file-export warning</strong><p>{job.data.warning}</p></div>
        </div>
      )}
      {reviseConsultation.error && <ErrorPanel error={reviseConsultation.error} />}
      {failed && (
        <div className="notice notice--error">
          <AlertTriangle size={19} />
          <div>
            <strong>Consultation failed at {job.data?.current_stage?.replaceAll("_", " ") || run.data?.failure_stage}</strong>
            {!failureDiagnostics.length && (
              <p>{job.data?.error || run.data?.sanitized_errors.join(" ")}</p>
            )}
            <FailureDiagnostics diagnostics={failureDiagnostics} />
          </div>
        </div>
      )}

      <CompassTrail
        events={events.data || []}
        currentStage={job.data?.current_stage}
        status={status as JobStatus}
      />

      {active && (
        <section className="live-analysis" aria-live="polite">
          <div className="live-analysis__header">
            <Activity size={18} />
            <div>
              <span className="eyebrow">Structured analysis trace</span>
              <h2>What Arch Compass has established so far</h2>
            </div>
          </div>
          <EventTimeline events={events.data || []} compact />
        </section>
      )}

      {run.data && (
        <>
          <nav className="tabs" aria-label="Run views">
            {[
              ["recommendation", "Recommendation"],
              ["report", "Full report"],
              ["trace", "Analysis trace"],
              ["evidence", "Evidence"],
              ["details", "Run details"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={tab === value ? "active" : ""}
                onClick={() => setTab(value as Tab)}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="tab-panel">
            {tab === "recommendation" && report && (
              <ArchitectureWorkspace
                architectureCase={architectureCase.data?.snapshot}
                run={run.data}
                report={report}
                onClaim={setSelectedClaim}
              />
            )}
            {tab === "report" && (
              <div className="markdown report-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {run.data.markdown_report || "_No Markdown report was produced._"}
                </ReactMarkdown>
              </div>
            )}
            {tab === "trace" && <EventTimeline events={events.data || eventsFromRun(run.data)} />}
            {tab === "evidence" && report && (
              <EvidenceView report={report} onClaim={setSelectedClaim} />
            )}
            {tab === "details" && <RunDetails run={run.data} />}
          </div>
        </>
      )}

      {selectedClaim && (
        <EvidenceDrawer
          claim={selectedClaim}
          packets={run.data?.focused_packets || []}
          onClose={() => setSelectedClaim(null)}
        />
      )}
    </div>
  );
}

function CompassTrail({
  events,
  currentStage,
  status,
}: {
  events: ProgressEvent[];
  currentStage?: string | null;
  status: JobStatus;
}) {
  const completedStages = new Set(
    events
      .filter((event) => event.event_type === "stage_completed")
      .map((event) => event.stage),
  );
  const currentIndex = stageGroups.findIndex((group) =>
    group.stages.includes(currentStage || ""),
  );
  return (
    <section className="compass-trail" aria-label="Consultation progress">
      <div className="compass-trail__line" />
      {stageGroups.map((group, index) => {
        const complete =
          group.stages.some((stage) => completedStages.has(stage)) &&
          (index < currentIndex || ["succeeded", "succeeded_with_warnings"].includes(status));
        const active = group.stages.includes(currentStage || "") && ["queued", "running"].includes(status);
        const Icon = group.icon;
        return (
          <div
            key={group.label}
            className={`trail-step ${complete ? "trail-step--complete" : ""} ${active ? "trail-step--active" : ""}`}
          >
            <span>{complete ? <Check size={16} /> : <Icon size={16} />}</span>
            <strong>{group.label}</strong>
          </div>
        );
      })}
    </section>
  );
}

function EventTimeline({ events, compact = false }: { events: ProgressEvent[]; compact?: boolean }) {
  const visible = compact ? events.filter((event) => event.event_type === "artifact_available").slice(-4) : events;
  return (
    <div className={`event-timeline ${compact ? "event-timeline--compact" : ""}`}>
      {visible.map((event) => (
        <article className={`event event--${event.event_type}`} key={event.sequence}>
          <span className="event__marker">
            {event.event_type === "artifact_available" ? <Sparkles size={14} /> : <Circle size={10} />}
          </span>
          <div>
            <small>{event.stage?.replaceAll("_", " ") || "queue"} · {formatDate(event.occurred_at)}</small>
            <h3>{event.title}</h3>
            {event.summary && <p>{event.summary}</p>}
            {!compact && event.event_type === "artifact_available" && Object.keys(event.data).length > 0 && (
              <details>
                <summary>Inspect structured artifact</summary>
                <pre>{JSON.stringify(event.data, null, 2)}</pre>
              </details>
            )}
          </div>
        </article>
      ))}
      {!visible.length && <p className="muted">The first structured artifact will appear here.</p>}
    </div>
  );
}

function EvidenceView({
  report,
  onClaim,
}: {
  report: RecommendationReport;
  onClaim: (claim: Claim) => void;
}) {
  const sections = [
    ["Repository observations", report.repository_observations, FileCode2],
    ["Policy guidance", report.relevant_policies, BookOpenText],
    ["Confirmed context", report.confirmed_context, CircleCheck],
    ["Assumptions and questions", report.assumptions_and_unresolved_questions, AlertTriangle],
  ] as const;
  return (
    <div className="evidence-sections">
      {sections.map(([title, claims, Icon]) => (
        <section key={title} className="report-section">
          <div className="section-heading">
            <div><span className="eyebrow">Classified claims</span><h2>{title}</h2></div>
            <Icon size={21} />
          </div>
          <div className="claim-list">
            {claims.map((claim) => (
              <button key={claim.claim_id} type="button" onClick={() => onClaim(claim)}>
                <span>{claim.classification.replaceAll("_", " ")}</span>
                <p>{claim.text}</p>
                <small>{shortId(claim.claim_id)} · {claim.atlas_references.length + claim.policy_ids.length} references</small>
              </button>
            ))}
            {!claims.length && <p className="muted">No claims in this classification.</p>}
          </div>
        </section>
      ))}
    </div>
  );
}

function EvidenceDrawer({
  claim,
  packets,
  onClose,
}: {
  claim: Claim;
  packets: FocusedAnalysisPacket[];
  onClose: () => void;
}) {
  const dialogRef = useDialogFocus(onClose);
  const atlasEvidence = claim.atlas_references.map((reference) => {
    const packet = packets.find((item) =>
      item.node_evidence.some(
        (evidence) => evidence.node.node_id === reference.node_id,
      ) ||
      item.node_summaries.some((node) => node.node_id === reference.node_id),
    );
    const typedEvidence = packet?.node_evidence.find(
      (item) => item.node.node_id === reference.node_id,
    );
    const legacyNode = packet?.node_summaries.find(
      (item) => item.node_id === reference.node_id,
    );
    return {
      reference,
      node: typedEvidence?.node || legacyNode,
      selectionReasons:
        typedEvidence?.reasons || legacyNode?.selection_reasons || [],
      semanticMetrics: typedEvidence?.metrics || [],
      signals: typedEvidence?.signals || [],
      legacyMetrics: packet?.metrics.find(
        (item) => item.node_id === reference.node_id,
      ),
      relationshipEvidence:
        packet?.relationship_evidence.filter(
          (item) =>
            item.source.node_id === reference.node_id ||
            item.target.node_id === reference.node_id,
        ) || [],
      relationships:
        packet?.relationships.filter(
          (item) =>
            item.source_id === reference.node_id ||
            item.target_id === reference.node_id,
        ) || [],
      excerpts:
        packet?.excerpts.filter((item) => item.node_id === reference.node_id) || [],
    };
  });
  const policyEvidence = claim.policy_ids.map((policyId) => {
    const retrieved = packets
      .flatMap((packet) => packet.policies)
      .find((item) => item.policy.id === policyId);
    return { policyId, retrieved };
  });
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        ref={dialogRef}
        className="evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="drawer-close" type="button" onClick={onClose} aria-label="Close evidence"><X size={20} /></button>
        <Badge tone="teal">{claim.classification.replaceAll("_", " ")}</Badge>
        <h2 id="evidence-title">{claim.text}</h2>
        <code>{claim.claim_id}</code>
        <section>
          <span className="eyebrow">Repository references</span>
          {atlasEvidence.map(({
            reference,
            node,
            selectionReasons,
            semanticMetrics,
            signals,
            legacyMetrics,
            relationshipEvidence,
            relationships,
            excerpts,
          }) => (
            <details className="evidence-record" key={reference.node_id}>
              <summary className="reference-card">
                <FileCode2 size={18} />
                <div>
                  <strong>
                    {node?.qualified_name ||
                      reference.location?.path ||
                      reference.node_id}
                  </strong>
                  <code>
                    {(node?.location || reference.location)
                      ? `${node?.location?.path || reference.location?.path} · lines ${
                          node?.location?.start_line || reference.location?.start_line
                        }–${node?.location?.end_line || reference.location?.end_line}`
                      : reference.node_id}
                  </code>
                </div>
                <ChevronRight size={16} />
              </summary>
              <div className="evidence-record__body">
                {node && "summary" in node && node.summary && (
                  <p>{node.summary}</p>
                )}
                {selectionReasons.length > 0 && (
                  <div>
                    <span className="eyebrow">Why this node was surfaced</span>
                    <ul className="evidence-list">
                      {selectionReasons.map((reason, index) => (
                        <li key={`${reason.kind}-${index}`}>
                          <code>{reason.kind.replaceAll("_", " ")}</code>{" "}
                          {reason.explanation}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {semanticMetrics.length > 0 ? (
                  <div className="metric-groups">
                    {semanticMetrics
                      .filter((metric) => metric.value > 0)
                      .map((metric) => (
                        <div key={metric.metric}>
                          <strong>
                            {metric.nature === "structural_proxy"
                              ? "Structural proxy"
                              : "Objective measurement"}
                          </strong>
                          <span>
                            {metric.metric.replaceAll("_", " ").replaceAll(".", " · ")}
                            <b>{metric.value}</b>
                          </span>
                          {metric.definition && <small>{metric.definition}</small>}
                          <small>
                            Scope: {metric.scope.replaceAll("_", " ")}
                            {metric.limitations
                              ? ` · ${metric.limitations}`
                              : ""}
                          </small>
                        </div>
                      ))}
                  </div>
                ) : legacyMetrics ? (
                  <div className="metric-groups">
                    {Object.entries({
                      Local: legacyMetrics.local,
                      Dependency: legacyMetrics.dependency,
                      "Change amplification": legacyMetrics.change_amplification,
                      "Cognitive scope": legacyMetrics.cognitive_scope,
                    }).map(([label, values]) => (
                      <div key={label}>
                        <strong>{label}</strong>
                        {Object.entries(values)
                          .filter(
                            ([, value]) =>
                              typeof value === "number" && value > 0,
                          )
                          .map(([name, value]) => (
                            <span key={name}>
                              {name.replaceAll("_", " ")} <b>{value}</b>
                            </span>
                          ))}
                      </div>
                    ))}
                  </div>
                ) : null}
                {(relationshipEvidence.length > 0 || relationships.length > 0) && (
                  <div>
                    <span className="eyebrow">Persisted relationships</span>
                    <ul className="evidence-list">
                      {relationshipEvidence.map((relationship) => (
                        <li key={relationship.edge_id}>
                          <code>{relationship.edge_type}</code>{" "}
                          {relationship.source.node_id === reference.node_id
                            ? `→ ${relationship.target.qualified_name}`
                            : `${relationship.source.qualified_name} →`}
                        </li>
                      ))}
                      {!relationshipEvidence.length && relationships.map((relationship) => (
                        <li key={relationship.edge_id}>
                          <code>{relationship.edge_type}</code>{" "}
                          {relationship.source_id === reference.node_id
                            ? `→ ${relationship.target_id}`
                            : `${relationship.source_id} →`}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {signals.length > 0 && (
                  <div>
                    <span className="eyebrow">Objective signals</span>
                    <ul className="evidence-list">
                      {signals.map((signal, index) => (
                        <li key={`${signal.code}-${index}`}>
                          <code>{signal.code.replaceAll("-", " ")}</code>{" "}
                          {signal.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {excerpts.map((excerpt) => (
                  <div key={`${excerpt.node_id}-${excerpt.location.start_line}`}>
                    <span className="eyebrow">
                      Persisted excerpt · lines {excerpt.location.start_line}–
                      {excerpt.location.end_line}
                    </span>
                    <pre className="source-excerpt">{excerpt.text}</pre>
                  </div>
                ))}
              </div>
            </details>
          ))}
          {!claim.atlas_references.length && <p className="muted">No repository evidence attached.</p>}
        </section>
        <section>
          <span className="eyebrow">Policy references</span>
          {policyEvidence.map(({ policyId, retrieved }) => (
            <details className="evidence-record" key={policyId}>
              <summary className="reference-card">
                <BookOpenText size={18} />
                <div>
                  <strong>{retrieved?.policy.title || policyId}</strong>
                  <code>
                    {retrieved
                      ? `${retrieved.policy.strength} · ${policyApplicabilityLabel(
                          retrieved.policy.scope,
                          retrieved.policy.applies_to,
                        )}`
                      : policyId}
                  </code>
                </div>
                <ChevronRight size={16} />
              </summary>
              {retrieved && (
                <div className="evidence-record__body">
                  <p>
                    Authored by <strong>{retrieved.policy.source.author}</strong>
                    {retrieved.policy.source.inspiration.length
                      ? ` · inspired by ${retrieved.policy.source.inspiration.join(", ")}`
                      : ""}
                  </p>
                  <p>
                    Applies to{" "}
                    <strong>
                      {policyApplicabilityLabel(
                        retrieved.policy.scope,
                        retrieved.policy.applies_to,
                      )}
                    </strong>
                  </p>
                  {retrieved.chunks.map((chunk) => (
                    <div key={chunk.chunk_id} className="policy-match">
                      <span className="eyebrow">{chunk.section}</span>
                      <p>{chunk.text}</p>
                    </div>
                  ))}
                  <Link to="/policies" className="text-link">
                    Open policy library <ChevronRight size={14} />
                  </Link>
                </div>
              )}
            </details>
          ))}
          {!claim.policy_ids.length && <p className="muted">No policy guidance attached.</p>}
        </section>
        <div className="inspector-note">
          <Network size={18} />
          <p>This claim only cites evidence surfaced inside the consultation’s bounded packets.</p>
        </div>
      </aside>
    </div>
  );
}

function RunDetails({ run }: { run: ConsultationRun }) {
  return (
    <div className="details-grid">
      <Stat label="Reasoning model" value={run.reasoning_model} />
      <Stat label="Embedding model" value={run.embedding_model} />
      <Stat label="Atlas" value={run.atlas_version_id ? shortId(run.atlas_version_id) : "Greenfield"} />
      <Stat label="Policy index" value={run.policy_index_version_id ? shortId(run.policy_index_version_id) : "—"} />
      <section className="report-section details-grid__wide">
        <span className="eyebrow">Stage timings</span>
        <div className="timing-list">
          {Object.entries(run.stage_timings).map(([stage, seconds]) => (
            <div key={stage}>
              <span>{stage.replaceAll("_", " ")}</span>
              <span className="timing-bar"><i style={{ width: `${Math.min(100, seconds * 8 + 4)}%` }} /></span>
              <strong>{seconds.toFixed(2)}s</strong>
            </div>
          ))}
        </div>
      </section>
      <section className="report-section details-grid__wide">
        <span className="eyebrow">Execution metadata</span>
        <pre>{JSON.stringify(run.execution_metadata, null, 2)}</pre>
      </section>
    </div>
  );
}

function duration(start: string, end: string) {
  const seconds = Math.max(0, (new Date(end).getTime() - new Date(start).getTime()) / 1000);
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export function ElapsedTime({
  active,
  start,
  end,
}: {
  active: boolean;
  start?: string | null;
  end?: string | null;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active || !start || end) return;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(interval);
  }, [active, end, start]);

  if (!start) return <>Waiting</>;
  return <>{duration(start, end || new Date(now).toISOString())}</>;
}

function eventsFromRun(run: ConsultationRun): ProgressEvent[] {
  return Object.entries(run.stage_timings).map(([stage, seconds], index) => ({
    run_id: run.run_id,
    sequence: index + 1,
    event_type: "stage_completed",
    stage,
    title: `${stage.replaceAll("_", " ")} completed`,
    summary: `${seconds.toFixed(2)} seconds`,
    data: {},
    occurred_at: run.completed_at,
  }));
}
