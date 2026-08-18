import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { coreApi, type Review } from "../api";
import { AtlasExplorer } from "../components/atlas-explorer";
import { ConversationPanel } from "../components/conversation-panel";
import { FindingsPanel } from "../components/findings-panel";
import { QuestionsPanel } from "../components/questions-panel";
import { RevisionRail } from "../components/revision-rail";
import { Button, Card, ErrorNotice, Loading, Metric, PageTitle, SectionHeading, StatusBadge, Tabs } from "../components/ui";

function Overview({ review }: { review: Review }) {
  const material = review.findings.filter((item) => item.verdict === "material").length;
  const held = review.findings.filter((item) => item.verdict === "held").length;
  const cleared = review.findings.filter((item) => item.verdict === "cleared").length;
  return <div className="grid gap-5">
    <Card><div className="grid grid-cols-2 gap-6 sm:grid-cols-4"><Metric label="Candidates" value={review.findings.length} /><Metric label="Material" value={material} /><Metric label="Held" value={held} /><Metric label="Cleared" value={cleared} /></div></Card>
    <Card>
      <SectionHeading title="Architecture case" description={`Case revision ${review.case.revision} supplies the human context for this judgment.`} />
      <p className="mt-5 max-w-4xl font-display text-lg leading-8 text-ink">{review.case.goal || "The architecture goal has not yet been stated."}</p>
      <div className="mt-6 grid gap-6 border-t border-rule pt-6 md:grid-cols-2">
        <div><h3 className="text-xs font-bold uppercase tracking-[0.12em] text-ink-3">Constraints</h3>{review.case.constraints.length ? <div className="mt-3 grid gap-3">{review.case.constraints.map((item, index) => <div key={index} className="rounded-xl bg-canvas-strong/55 p-3 text-sm leading-6"><span className="mr-2 font-semibold text-primary">{item.facet.replaceAll("_", " ")}</span>{item.text}</div>)}</div> : <p className="mt-3 text-sm text-ink-3">None recorded.</p>}</div>
        <div><h3 className="text-xs font-bold uppercase tracking-[0.12em] text-ink-3">Contextual decisions</h3>{review.case.decisions.length ? <div className="mt-3 grid gap-3">{review.case.decisions.map((item, index) => <div key={index} className="rounded-xl bg-canvas-strong/55 p-3 text-sm leading-6">{item.text}</div>)}</div> : <p className="mt-3 text-sm text-ink-3">None recorded.</p>}</div>
      </div>
      {review.case.answers.length ? <details className="mt-6 border-t border-rule pt-5"><summary className="text-sm font-semibold">Recorded clarifications · {review.case.answers.length}</summary><div className="mt-4 grid gap-3">{review.case.answers.map((answer) => <div key={answer.question.id} className="rounded-xl border border-rule p-4 text-sm"><div className="font-semibold">{answer.question.text}</div><div className="mt-1 leading-6 text-ink-2">{answer.status === "skipped" ? "Explicitly skipped" : answer.value}</div></div>)}</div></details> : null}
    </Card>
    <Card>
      <SectionHeading title="Change since the prior review" description={review.previous_review_id ? "Candidate identity and provenance are compared against the preceding immutable review." : "This is the first recorded review in this lineage."} />
      <div className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4"><Metric label="Unchanged" value={review.delta.unchanged.length} /><Metric label="Changed" value={review.delta.changed.length} /><Metric label="New" value={review.delta.new.length} /><Metric label="Addressed" value={review.delta.addressed.length} /></div>
      {review.delta.changed.length ? <div className="mt-6 grid gap-2 border-t border-rule pt-5">{review.delta.changed.map((item) => <div key={item.candidate_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-canvas-strong/55 p-3 text-sm"><span className="font-mono text-xs">{item.candidate_id.slice(0, 12)}</span><span className="text-ink-2">{item.causes.join(", ")}</span></div>)}</div> : null}
    </Card>
  </div>;
}

function EvidenceTab({ review }: { review: Review }) {
  const evidence = useQuery({ queryKey: ["review-source", review.id], queryFn: () => coreApi.reviewSource(review.id) });
  if (evidence.isLoading) return <Loading label="Loading pinned evidence…" />;
  if (evidence.error) return <ErrorNotice error={evidence.error} />;
  return <div className="grid gap-4">{evidence.data?.map((item, index) => <article key={`${item.location?.path}-${index}`} className="overflow-hidden rounded-2xl border border-rule bg-surface shadow-card"><div className="border-b border-rule px-5 py-4"><div className="font-semibold">{item.description}</div>{item.location ? <div className="mt-1 font-mono text-xs text-ink-3">{item.location.path}:{item.location.start_line}-{item.location.end_line}</div> : null}</div>{item.excerpt ? <pre className="overflow-x-auto bg-[#151922] p-5 text-xs leading-5 text-[#dce3ef]"><code>{item.excerpt}</code></pre> : <p className="p-5 text-sm text-ink-3">No excerpt available.</p>}</article>)}</div>;
}

function ReportTab({ review }: { review: Review }) {
  const report = useQuery({ queryKey: ["review-report", review.id], queryFn: () => coreApi.reviewReport(review.id), enabled: review.status === "completed" });
  if (review.status !== "completed") return <Card tone="subtle"><p className="text-sm text-ink-3">A rendered report becomes available when the review completes.</p></Card>;
  if (report.isLoading) return <Loading label="Rendering report…" />;
  if (report.error) return <ErrorNotice error={report.error} />;
  return <Card><div className="mb-5 flex justify-end"><a href={`/api/reviews/${encodeURIComponent(review.id)}/report`} download={`archcompass-${review.id}.md`} className="rounded-xl border border-rule-strong px-3 py-2 text-xs font-semibold hover:border-primary/40">Download Markdown</a></div><pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-ink-2">{report.data}</pre></Card>;
}

function ProvenanceTab({ review }: { review: Review }) {
  return <div className="grid gap-4">{review.retrieval_manifest.map((item) => <Card key={item.candidate_id}><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs font-bold uppercase tracking-[0.12em] text-primary">Candidate {item.candidate_id.slice(0, 12)}</div><h2 className="mt-1 font-display text-lg font-semibold">{item.retriever} <span className="font-normal text-ink-3">v{item.version}</span></h2></div><span className="max-w-full break-all rounded-lg bg-canvas-strong px-2 py-1 font-mono text-[10px] text-ink-3">{item.model_identity || "non-embedding strategy"}</span></div><div className="mt-5"><div className="text-xs font-bold uppercase tracking-[0.12em] text-ink-3">Selected policies</div><div className="mt-2 flex flex-wrap gap-2">{item.selected_policy_ids.length ? item.selected_policy_ids.map((id) => <span key={id} className="rounded-full border border-rule px-2.5 py-1 font-mono text-xs text-ink-2">{id}</span>) : <span className="text-sm text-ink-3">None</span>}</div></div><dl className="mt-5 grid gap-3 border-t border-rule pt-4 text-xs text-ink-3"><div><dt className="font-semibold text-ink-2">Corpus fingerprint</dt><dd className="mt-1 break-all font-mono">{item.corpus_fingerprint}</dd></div>{item.query_fingerprint ? <div><dt className="font-semibold text-ink-2">Query fingerprint</dt><dd className="mt-1 break-all font-mono">{item.query_fingerprint}</dd></div> : null}{Object.entries(item.metadata).map(([key, value]) => <div key={key}><dt className="font-semibold text-ink-2">{key}</dt><dd className="mt-1 break-all font-mono">{value}</dd></div>)}</dl></Card>)}</div>;
}

export function ReviewPage() {
  const { reviewId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [tab, setTab] = useState("overview");
  const review = useQuery({ queryKey: ["review", reviewId], queryFn: () => coreApi.review(reviewId) });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: coreApi.reviews });
  const cancel = useMutation({ mutationFn: () => coreApi.cancel(reviewId), onSuccess: async (next) => { await client.invalidateQueries({ queryKey: ["reviews"] }); navigate(`/reviews/${next.id}`); } });
  if (review.isLoading) return <Loading label="Opening review…" />;
  if (review.error || !review.data) return <ErrorNotice error={review.error || new Error("Review not found")} />;

  const value = review.data;
  const tabs = [{ id: "overview", label: "Overview" }, { id: "findings", label: "Findings", count: value.findings.length }, { id: "atlas", label: "Atlas" }, { id: "evidence", label: "Evidence" }, { id: "report", label: "Report" }, { id: "provenance", label: "Retrieval", count: value.retrieval_manifest.length }, { id: "conversation", label: "Conversation" }];
  const atlasTerms = value.findings.flatMap((finding) => finding.candidate.participants.map((participant) => participant.qualified_name));

  return <div>
    <PageTitle eyebrow={`Review ${value.sequence} · Case revision ${value.case.revision}`} title={value.case.goal || "Architecture review"} description={`${value.repository.branch || "Bare folder"}${value.repository.commit ? ` · ${value.repository.commit.slice(0, 10)}` : ""}`}>
      <StatusBadge status={value.status} />
      {value.status === "awaiting_answers" ? <Button variant="danger" size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Cancel review</Button> : null}
    </PageTitle>
    {value.failure ? <div className="mb-5"><ErrorNotice error={new Error(value.failure)} /></div> : null}
    <div className="grid gap-6 xl:grid-cols-[230px_minmax(0,1fr)]">
      <aside className="grid content-start gap-4">
        <RevisionRail current={value} reviews={reviews.data || [value]} />
        <Card className="p-4 sm:p-4"><div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3">Repository snapshot</div><div className="mt-2 break-all font-mono text-[11px] leading-5 text-ink-2">{value.repository.path}</div><div className="mt-4 grid grid-cols-2 gap-3 border-t border-rule pt-4"><Metric label="Nodes" value={value.atlas.node_count} /><Metric label="Edges" value={value.atlas.edge_count} /></div></Card>
      </aside>
      <div className="min-w-0"><Tabs active={tab} onChange={setTab} items={tabs} ariaLabel="Review sections" /><div id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="mt-6">{value.status === "awaiting_answers" && tab === "overview" ? <QuestionsPanel review={value} /> : tab === "overview" ? <Overview review={value} /> : tab === "findings" ? <FindingsPanel review={value} /> : tab === "atlas" ? <AtlasExplorer root={value.repository.path} initialTerms={atlasTerms} /> : tab === "evidence" ? <EvidenceTab review={value} /> : tab === "report" ? <ReportTab review={value} /> : tab === "provenance" ? <ProvenanceTab review={value} /> : <ConversationPanel reviewId={value.id} />}</div></div>
    </div>
  </div>;
}
