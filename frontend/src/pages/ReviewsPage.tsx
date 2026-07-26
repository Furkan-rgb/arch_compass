import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CircleCheck, FlaskConical, Play } from "lucide-react";
import { useState } from "react";
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
import type { BundledCase } from "../types";

/**
 * Reviews, and the shortest path to producing one.
 *
 * The example picker exists because writing an ArchitectureCase by hand is the first
 * thing anyone has to do and the largest obstacle to trying the tool at all. Loading an
 * example indexes its repository and creates the case in one step, so a fresh workspace
 * can produce a real review immediately.
 */
export function ReviewsPage() {
  const client = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const examples = useQuery({ queryKey: ["bundled-cases"], queryFn: api.bundledCases });

  const run = useMutation({
    mutationFn: async (example: BundledCase) => {
      setNotice(`Loading ${example.title}…`);
      const revision = await api.loadBundledCase(example.name);
      setNotice(
        `Reviewing ${example.title}. One model call per boundary, so this takes a few minutes.`,
      );
      return api.createReview(revision.case_id, example.repository_root);
    },
    onSuccess: async (review) => {
      setNotice(null);
      await client.invalidateQueries({ queryKey: ["reviews"] });
      window.location.hash = "";
      window.location.assign(`/reviews/${review.review_id}`);
    },
    onError: () => setNotice(null),
  });

  return (
    <div className="page">
      <PageHeader
        eyebrow="Advice"
        title="Boundary reviews"
        description="Every boundary the detector finds, judged against one case."
      />

      <section className="panel">
        <h2 className="panel__title">Start from an example</h2>
        <p className="panel__hint">
          Each example ships a written case and a repository to run it against. One marked{" "}
          <em>scored</em> also ships the answers, so the review can be graded rather than
          only read.
        </p>
        {examples.isLoading ? <Loading label="Finding examples…" /> : null}
        {examples.isError ? <ErrorPanel error={examples.error} /> : null}
        <ul className="card-list">
          {(examples.data || []).map((example) => (
            <li key={example.name} className="card">
              <div className="card__body">
                <div className="card__heading">
                  <strong>{example.title}</strong>
                  {example.has_expected_answers ? (
                    <Badge tone="teal">
                      <FlaskConical size={13} aria-hidden /> scored
                    </Badge>
                  ) : null}
                </div>
                <p className="card__detail">{example.problem_statement}</p>
                <code className="card__meta">{example.repository_root}</code>
              </div>
              <button
                type="button"
                className="button button--primary"
                disabled={run.isPending}
                onClick={() => run.mutate(example)}
              >
                <Play size={15} aria-hidden /> Review this
              </button>
            </li>
          ))}
        </ul>
        {notice ? <p className="panel__notice">{notice}</p> : null}
        {run.isError ? <ErrorPanel error={run.error} /> : null}
      </section>

      <section className="panel">
        <h2 className="panel__title">Past reviews</h2>
        {reviews.isLoading ? <Loading label="Reading reviews…" /> : null}
        {reviews.isError ? <ErrorPanel error={reviews.error} /> : null}
        {reviews.data && reviews.data.length === 0 ? (
          <EmptyState
            title="No reviews yet"
            description="Run one of the examples above to produce the first."
          />
        ) : null}
        <ul className="card-list">
          {(reviews.data || []).map((review) => (
            <li key={review.review_id} className="card">
              <div className="card__body">
                <div className="card__heading">
                  <strong>{shortId(review.review_id)}</strong>
                  <Badge tone={review.boundaries_material > 0 ? "warning" : "success"}>
                    {review.boundaries_material > 0 ? (
                      <>{review.boundaries_material} material</>
                    ) : (
                      <>
                        <CircleCheck size={13} aria-hidden /> all cleared
                      </>
                    )}
                  </Badge>
                </div>
                {/* The examined count is shown even when nothing was material: a review
                    that cleared six boundaries and one that found none are different
                    results, and only this number tells them apart. */}
                <p className="card__detail">
                  {review.boundaries_reviewed} boundaries examined ·{" "}
                  {formatDate(review.created_at)}
                </p>
              </div>
              <Link className="button" to={`/reviews/${review.review_id}`}>
                Open <ArrowRight size={15} aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
