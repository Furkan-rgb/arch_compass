import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CircleAlert, CircleCheck, Clock3, Play } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../api";
import {
  Badge,
  EmptyState,
  ErrorPanel,
  Loading,
  PageHeader,
  formatDate,
  shortId,
} from "../components";

export function RunsPage() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: (query) =>
      query.state.data?.some((job) => ["queued", "running"].includes(job.status))
        ? 1_500
        : false,
  });

  const activeIds = new Set((runs.data || []).map((run) => run.run_id));
  const entries = [
    ...(jobs.data || [])
      .filter((job) => !activeIds.has(job.run_id))
      .map((job) => ({
        run_id: job.run_id,
        case_id: job.case_id,
        status: job.status,
        disposition: null,
        failure_stage: job.current_stage,
        completed_at: job.completed_at || job.updated_at,
        input_case_revision: job.input_case_revision,
      })),
    ...(runs.data || []),
  ];

  return (
    <div className="page">
      <PageHeader
        eyebrow="Immutable consultation record"
        title="Runs and reports"
        description="Follow active work or reopen the complete evidence and validation history."
        action={<Link to="/new" className="button button--primary"><Play size={16} /> New consultation</Link>}
      />
      {(runs.isLoading || jobs.isLoading) && <Loading />}
      {(runs.error || jobs.error) && <ErrorPanel error={runs.error || jobs.error} />}
      {!entries.length && !runs.isLoading && !jobs.isLoading && (
        <EmptyState
          icon={<Clock3 size={30} />}
          title="No consultations yet"
          description="A run records every structured stage, evidence packet, and report."
          action={<Link to="/new" className="button button--secondary">Start consultation</Link>}
        />
      )}
      <div className="run-table" role="list">
        {entries.map((run) => {
          const succeeded = run.status === "succeeded" || run.status === "succeeded_with_warnings";
          const active = run.status === "queued" || run.status === "running";
          return (
            <Link to={`/runs/${run.run_id}`} className="run-row" key={run.run_id} role="listitem">
              <span className={`run-row__status run-row__status--${active ? "active" : succeeded ? "success" : "failed"}`}>
                {active ? <Play size={17} /> : succeeded ? <CircleCheck size={18} /> : <CircleAlert size={18} />}
              </span>
              <div>
                <strong>{run.disposition?.replaceAll("_", " ") || run.status.replaceAll("_", " ")}</strong>
                <small>{shortId(run.run_id)} · case rev {run.input_case_revision}</small>
              </div>
              <Badge tone={active ? "teal" : succeeded ? "success" : "danger"}>{run.status}</Badge>
              <span>{run.failure_stage?.replaceAll("_", " ") || "Report complete"}</span>
              <time>{formatDate(run.completed_at)}</time>
              <ArrowRight size={17} />
            </Link>
          );
        })}
      </div>
    </div>
  );
}
