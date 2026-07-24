import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpenText, Compass, Play } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

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

export function CasesPage() {
  const navigate = useNavigate();
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const start = useMutation({
    mutationFn: ({ caseId, repositoryRoot }: { caseId: string; repositoryRoot?: string }) =>
      api.startConsultation(caseId, repositoryRoot),
    onSuccess: (job) => navigate(`/runs/${job.run_id}`),
  });

  return (
    <div className="page">
      <PageHeader
        eyebrow="Decision notebook"
        title="Architecture cases"
        description="Every consultation starts from a specific, immutable case revision."
        action={<Link to="/new" className="button button--primary"><Compass size={17} /> New case</Link>}
      />
      {cases.isLoading && <Loading />}
      {cases.error && <ErrorPanel error={cases.error} />}
      {start.error && <ErrorPanel error={start.error} />}
      {cases.data && !cases.data.length && (
        <EmptyState
          icon={<BookOpenText size={30} />}
          title="No architecture cases"
          description="Frame a greenfield decision, point at a repository, or import case YAML."
          action={<Link to="/new" className="button button--secondary">Start consultation</Link>}
        />
      )}
      <div className="card-grid">
        {cases.data?.map((item) => (
          <article className="case-card" key={item.case_id}>
            <div className="case-card__top">
              <Badge tone={item.repository_root ? "teal" : "neutral"}>
                {item.repository_root ? "Brownfield" : "Greenfield"}
              </Badge>
              <span>rev {item.revision}</span>
            </div>
            <h2>{item.title}</h2>
            <p>{item.problem_statement}</p>
            {item.current_recommendation && (
              <div className="decision-preview">
                <span>Current recommendation</span>
                <strong>{item.current_recommendation.summary}</strong>
              </div>
            )}
            <dl className="meta-pairs">
              <div><dt>Case</dt><dd title={item.case_id}>{shortId(item.case_id)}</dd></div>
              <div><dt>Updated</dt><dd>{formatDate(item.updated_at)}</dd></div>
              {item.confidence && <div><dt>Confidence</dt><dd>{item.confidence.level}</dd></div>}
            </dl>
            <div className="card-actions">
              {item.current_recommendation?.run_id && (
                <Link className="button button--quiet" to={`/runs/${item.current_recommendation.run_id}`}>
                  Open report <ArrowRight size={15} />
                </Link>
              )}
              <button
                className="button button--secondary"
                type="button"
                disabled={start.isPending}
                onClick={() =>
                  start.mutate({
                    caseId: item.case_id,
                    repositoryRoot: item.repository_root || undefined,
                  })
                }
              >
                <Play size={15} /> Run again
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
