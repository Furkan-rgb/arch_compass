import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConversationPanel } from "../components/conversation-panel";
import { AtlasExplorer } from "../components/atlas-explorer";
import { FindingsPanel } from "../components/findings-panel";
import { QuestionsPanel } from "../components/questions-panel";
import { RevisionRail } from "../components/revision-rail";
import { ErrorNotice, Loading, Metric, PageTitle, StatusBadge, Tabs } from "../components/ui";
import { coreApi, type Review } from "../api";

function Overview({ review }: { review: Review }) {
  const material = review.findings.filter((item) => item.verdict === "material").length;
  const held = review.findings.filter((item) => item.verdict === "held").length;
  return <div className="grid gap-5"><section className="rounded-xl border border-rule bg-surface p-6"><div className="grid grid-cols-2 gap-5 sm:grid-cols-4"><Metric label="Candidates" value={review.findings.length} /><Metric label="Material" value={material} /><Metric label="Held" value={held} /><Metric label="Addressed" value={review.delta.addressed.length} /></div></section><section className="rounded-xl border border-rule bg-surface p-6"><h2 className="font-display text-xl font-semibold">Architecture case</h2><p className="mt-3 leading-7 text-ink-2">{review.case.goal || "The goal has not yet been stated."}</p><div className="mt-5 grid gap-4 md:grid-cols-2"><div><h3 className="text-xs font-semibold uppercase tracking-wide text-ink-3">Constraints</h3>{review.case.constraints.length ? review.case.constraints.map((item, index) => <p key={index} className="mt-2 text-sm"><span className="text-primary">{item.facet}</span> · {item.text}</p>) : <p className="mt-2 text-sm text-ink-3">None recorded.</p>}</div><div><h3 className="text-xs font-semibold uppercase tracking-wide text-ink-3">Contextual decisions</h3>{review.case.decisions.length ? review.case.decisions.map((item, index) => <p key={index} className="mt-2 text-sm">{item.text}</p>) : <p className="mt-2 text-sm text-ink-3">None recorded.</p>}</div></div>{review.case.answers.length ? <div className="mt-6 border-t border-rule pt-5"><h3 className="text-xs font-semibold uppercase tracking-wide text-ink-3">Clarifications already recorded</h3>{review.case.answers.map((answer) => <div key={answer.question.id} className="mt-3 text-sm"><div className="font-medium">{answer.question.text}</div><div className="mt-1 text-ink-2">{answer.status === "skipped" ? "Explicitly skipped" : answer.value}</div></div>)}</div> : null}</section><section className="rounded-xl border border-rule bg-surface p-6"><h2 className="font-display text-xl font-semibold">Delta from prior review</h2><div className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-4"><Metric label="Unchanged" value={review.delta.unchanged.length} /><Metric label="Changed" value={review.delta.changed.length} /><Metric label="New" value={review.delta.new.length} /><Metric label="Addressed" value={review.delta.addressed.length} /></div>{review.delta.changed.length ? <div className="mt-5 grid gap-2">{review.delta.changed.map((item) => <div key={item.candidate_id} className="rounded-md bg-canvas p-3 text-sm"><span className="font-mono text-xs">{item.candidate_id.slice(0, 12)}</span><span className="ml-3 text-ink-2">{item.causes.join(", ")}</span></div>)}</div> : null}</section></div>;
}

function EvidenceTab({ review }: { review: Review }) {
  const evidence = useQuery({ queryKey: ["review-source", review.id], queryFn: () => coreApi.reviewSource(review.id) });
  if (evidence.isLoading) return <Loading label="Loading pinned evidence…" />;
  if (evidence.error) return <ErrorNotice error={evidence.error} />;
  return <div className="grid gap-4">{evidence.data?.map((item, index) => <article key={`${item.location?.path}-${index}`} className="rounded-xl border border-rule bg-surface p-5"><div className="font-medium">{item.description}</div>{item.location ? <div className="mt-1 font-mono text-xs text-ink-3">{item.location.path}:{item.location.start_line}-{item.location.end_line}</div> : null}{item.excerpt ? <pre className="mt-4 overflow-x-auto rounded-lg bg-[#171b20] p-4 text-xs leading-5 text-[#d8dee9]"><code>{item.excerpt}</code></pre> : <p className="mt-3 text-sm text-ink-3">No excerpt available.</p>}</article>)}</div>;
}

function ReportTab({ review }: { review: Review }) {
  const report = useQuery({ queryKey: ["review-report", review.id], queryFn: () => coreApi.reviewReport(review.id), enabled: review.status === "completed" });
  if (review.status !== "completed") return <div className="rounded-xl border border-dashed border-rule p-8 text-sm text-ink-3">A rendered report is available when the review completes.</div>;
  if (report.isLoading) return <Loading label="Rendering report…" />;
  if (report.error) return <ErrorNotice error={report.error} />;
  return <article className="rounded-xl border border-rule bg-surface p-6"><div className="mb-5 flex justify-end"><a href={`/api/reviews/${encodeURIComponent(review.id)}/report`} download={`archcompass-${review.id}.md`} className="rounded-md border border-rule px-3 py-2 text-xs font-medium">Download Markdown</a></div><pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-ink-2">{report.data}</pre></article>;
}

function ProvenanceTab({ review }: { review: Review }) {
  return <div className="grid gap-4">{review.retrieval_manifest.map((item) => <article key={item.candidate_id} className="rounded-xl border border-rule bg-surface p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-wide text-primary">Candidate {item.candidate_id.slice(0, 12)}</div><h2 className="mt-1 font-display text-lg font-semibold">{item.retriever} <span className="text-ink-3">v{item.version}</span></h2></div><span className="font-mono text-xs text-ink-3">{item.model_identity || "non-embedding strategy"}</span></div><div className="mt-4 text-sm"><strong>Selected policies:</strong> {item.selected_policy_ids.join(", ") || "none"}</div><dl className="mt-4 grid gap-2 text-xs text-ink-3"><div><dt className="inline font-semibold">Corpus </dt><dd className="inline font-mono">{item.corpus_fingerprint}</dd></div>{item.query_fingerprint ? <div><dt className="inline font-semibold">Query </dt><dd className="inline font-mono">{item.query_fingerprint}</dd></div> : null}{Object.entries(item.metadata).map(([key, value]) => <div key={key}><dt className="inline font-semibold">{key} </dt><dd className="inline font-mono">{value}</dd></div>)}</dl></article>)}</div>;
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
  return <div><PageTitle eyebrow={`Review ${value.sequence} · Case revision ${value.case.revision}`} title={value.case.goal || "Architecture review"}><div className="flex items-center gap-3"><StatusBadge status={value.status} />{value.status === "awaiting_answers" ? <button onClick={() => cancel.mutate()} className="text-sm text-danger">Cancel</button> : null}</div></PageTitle>{value.failure ? <div className="mb-5"><ErrorNotice error={new Error(value.failure)} /></div> : null}<div className="grid gap-6 xl:grid-cols-[220px_minmax(0,1fr)]"><div className="grid content-start gap-4"><RevisionRail current={value} reviews={reviews.data || [value]} /><div className="rounded-xl border border-rule bg-surface p-4 text-xs text-ink-3"><div className="font-semibold uppercase tracking-wide">Repository</div><div className="mt-2 break-all font-mono">{value.repository.path}</div><div className="mt-2">{value.repository.branch || "bare folder"}{value.repository.commit ? ` · ${value.repository.commit.slice(0, 10)}` : ""}</div><div className="mt-4 grid grid-cols-2 gap-3"><div><strong className="block text-lg text-ink">{value.atlas.node_count}</strong>nodes</div><div><strong className="block text-lg text-ink">{value.atlas.edge_count}</strong>edges</div></div></div></div><div className="min-w-0"><Tabs active={tab} onChange={setTab} items={tabs} /><div className="mt-6">{value.status === "awaiting_answers" && tab === "overview" ? <QuestionsPanel review={value} /> : tab === "overview" ? <Overview review={value} /> : tab === "findings" ? <FindingsPanel review={value} /> : tab === "atlas" ? <AtlasExplorer root={value.repository.path} initialTerms={atlasTerms} /> : tab === "evidence" ? <EvidenceTab review={value} /> : tab === "report" ? <ReportTab review={value} /> : tab === "provenance" ? <ProvenanceTab review={value} /> : <ConversationPanel reviewId={value.id} />}</div></div></div></div>;
}
