import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpenText, Compass, Play } from "lucide-react";
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
    mutationFn: ({ caseId, repositoryRoot }: { caseId: string; repositoryRoot: string }) =>
      api.createReview(caseId, repositoryRoot),
    onSuccess: (review) => navigate(`/reviews/${review.review_id}`),
  });

  return (
    <div className="page">
      <PageHeader
        eyebrow="Decision notebook"
        title="Architecture cases"
        description="Every review starts from a specific, immutable case revision."
        action={<Link to="/reviews" className="button button--primary"><Compass size={17} /> Reviews</Link>}
      />
      {cases.isLoading && <Loading />}
      {cases.error && <ErrorPanel error={cases.error} />}
      {start.error && <ErrorPanel error={start.error} />}
      {cases.data && !cases.data.length && (
        <EmptyState
          icon={<BookOpenText size={30} />}
          title="No architecture cases"
          description="Frame a greenfield decision, point at a repository, or import case YAML."
          action={<Link to="/reviews" className="button button--secondary">Start a review</Link>}
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
            <dl className="meta-pairs">
              <div><dt>Case</dt><dd title={item.case_id}>{shortId(item.case_id)}</dd></div>
              <div><dt>Updated</dt><dd>{formatDate(item.updated_at)}</dd></div>
            </dl>
            <div className="card-actions">
              <button
                className="button button--secondary"
                type="button"
                disabled={start.isPending || !item.repository_root}
                title={
                  item.repository_root
                    ? undefined
                    : "This case has no indexed repository to review."
                }
                onClick={() =>
                  item.repository_root &&
                  start.mutate({
                    caseId: item.case_id,
                    repositoryRoot: item.repository_root,
                  })
                }
              >
                <Play size={15} /> Review
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
