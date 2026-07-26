import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  CircleCheck,
  CornerDownLeft,
  FlaskConical,
  MessageCircleQuestion,
  TriangleAlert,
  X,
} from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api";
import { ErrorPanel, Loading } from "../components";
import type { ReviewScore, ReviewedBoundary } from "../types";

/**
 * One boundary, as a block within a section rather than a card inside a card.
 *
 * The verdict is carried by a left rail rather than by a border and a background, so a
 * cleared boundary reads with the same weight as a material one. It is the record that the
 * advisor looked, and demoting it would make the page identical whether every boundary was
 * examined and cleared or none ever was.
 */
function Finding({ item, policyCount }: { item: ReviewedBoundary; policyCount: number }) {
  const bearings = item.policy_bearings || [];
  const abstraction = item.candidate.participants[0];
  const implementation = item.candidate.participants[1];
  return (
    <article className={`finding finding--${item.material ? "material" : "cleared"}`}>
      <header className="finding__head">
        <code className="finding__ref">{item.reference}</code>
        <h3 className="finding__title">{abstraction?.qualified_name}</h3>
      </header>

      {implementation ? (
        <p className="finding__where">
          Implemented only by <code>{implementation.qualified_name}</code>
          {implementation.location ? (
            <span className="finding__at">
              {implementation.location.path}:{implementation.location.start_line}
            </span>
          ) : null}
        </p>
      ) : null}

      <p className="finding__reasoning">{item.rationale}</p>

      {item.recommended_response ? (
        <p className="finding__action">
          <strong>Do this.</strong> {item.recommended_response}
        </p>
      ) : null}

      {bearings.length > 0 ? (
        <details className="finding__policies">
          {/* The denominator is named on purpose. Every policy was presented to every
              boundary, so one that does not appear here was considered and found not to
              apply — a different statement from never having been shown. */}
          <summary>
            {bearings.length} of {policyCount} policies apply
          </summary>
          <ul>
            {bearings.map((bearing) => (
              <li key={bearing.policy_id}>
                <strong>{bearing.policy_title}</strong> {bearing.how}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p className="finding__policies finding__policies--none">
          None of the {policyCount} policies presented bore on this boundary.
        </p>
      )}

      <p className="finding__limits">{item.candidate.limitations}</p>
    </article>
  );
}

function Score({ score }: { score: ReviewScore }) {
  return (
    <section className="scorebar">
      <p className="scorebar__head">
        <FlaskConical size={15} aria-hidden />
        <strong>
          {score.correct}/{score.total}
        </strong>
        <span>
          correct against the answers <code>{score.example}</code> ships
        </span>
      </p>
      <ul className="scorebar__rows">
        {score.boundaries.map((item) => (
          <li key={item.reference} className={item.correct ? "is-ok" : "is-bad"}>
            {item.correct ? (
              <CircleCheck size={13} aria-hidden />
            ) : (
              <X size={13} aria-hidden />
            )}
            <code>{item.reference}</code>
            <span className="scorebar__said">
              {item.actual ? "material" : "not material"}
              {item.correct
                ? ""
                : ` — expected ${item.expected ? "material" : "not material"}`}
            </span>
            {item.correct ? null : <span className="scorebar__why">{item.because}</span>}
          </li>
        ))}
      </ul>
      {score.unscored.length > 0 ? (
        <p className="scorebar__gap">
          Not scored, absent from the answer key: {score.unscored.join(", ")}
        </p>
      ) : null}
    </section>
  );
}

export function ReviewDetailPage() {
  const { reviewId = "" } = useParams();
  const client = useQueryClient();
  const [question, setQuestion] = useState("");
  const [open, setOpen] = useState(false);

  const review = useQuery({
    queryKey: ["review", reviewId],
    queryFn: () => api.review(reviewId),
    enabled: Boolean(reviewId),
  });
  const score = useQuery({
    queryKey: ["review-score", reviewId],
    queryFn: () => api.reviewScore(reviewId),
    enabled: Boolean(reviewId),
  });
  const conversations = useQuery({
    queryKey: ["review-conversations", reviewId],
    queryFn: () => api.reviewConversations(reviewId),
    enabled: Boolean(reviewId),
  });

  const conversation = conversations.data?.[0];
  const messages = conversation?.messages || [];

  const ask = useMutation({
    mutationFn: async (text: string) => {
      // Created on first use rather than alongside the review: a conversation with no
      // questions in it is an empty record that then has to be explained in a listing.
      const target = conversation ?? (await api.createReviewConversation(reviewId));
      if (!target.conversation_id) {
        throw new Error("The workspace returned a conversation without an identifier.");
      }
      return api.askReviewQuestion(target.conversation_id, text);
    },
    onSuccess: async () => {
      setQuestion("");
      setOpen(true);
      await client.invalidateQueries({ queryKey: ["review-conversations", reviewId] });
    },
  });

  if (review.isLoading) return <Loading label="Reading the review…" />;
  if (review.isError) return <ErrorPanel error={review.error} />;

  const report = review.data?.report;
  if (!report) {
    return <ErrorPanel error={new Error("This review did not produce a report.")} />;
  }

  const reviewed = report.reviewed || [];
  const policyCount = (report.policies_presented || []).length;
  const material = reviewed.filter((item) => item.material);
  const cleared = reviewed.filter((item) => !item.material);

  return (
    <div className="page page--review">
      <header className="review-head">
        <span className="eyebrow">Boundary review</span>
        <h1>{report.case_title}</h1>
        <p className="review-head__meta">
          <strong>{reviewed.length}</strong> boundaries examined ·{" "}
          <strong>{policyCount}</strong> policies presented to each ·{" "}
          <strong>{material.length}</strong> material, <strong>{cleared.length}</strong>{" "}
          earning their place
        </p>
        <p className="review-head__note">
          <code>BR-001</code> and the rest are references ArchCompass assigns in detection
          order. Cite one in a question and the answer cites it back.
        </p>
      </header>

      {score.data ? <Score score={score.data} /> : null}

      {material.length > 0 ? (
        <section className="group">
          <h2 className="group__title">
            <TriangleAlert size={16} aria-hidden /> Judged material
            <span className="group__count">{material.length}</span>
          </h2>
          <p className="group__hint">
            Each of these was found not to be earning its place under this case.
          </p>
          {material.map((item) => (
            <Finding key={item.reference} item={item} policyCount={policyCount} />
          ))}
        </section>
      ) : null}

      {cleared.length > 0 ? (
        <section className="group">
          <h2 className="group__title">
            <CircleCheck size={16} aria-hidden /> Earning their place
            <span className="group__count">{cleared.length}</span>
          </h2>
          <p className="group__hint">
            The advisor examined each of these and concluded it should stay as it is.
          </p>
          {cleared.map((item) => (
            <Finding key={item.reference} item={item} policyCount={policyCount} />
          ))}
        </section>
      ) : null}

      {/*
        `position: sticky; bottom: 0` and no JavaScript: the dock rides the bottom of the
        viewport while there is page left below it, then settles into its own place in the
        flow when you reach the end. Scroll position stays the single source of truth, so
        the dock cannot disagree with where the page actually is.
      */}
      <div className={`dock ${open ? "dock--open" : ""}`}>
        {messages.length > 0 ? (
          <button
            type="button"
            className="dock__toggle"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            <MessageCircleQuestion size={15} aria-hidden />
            {messages.length} {messages.length === 1 ? "question" : "questions"} asked
            <ChevronDown size={15} aria-hidden className="dock__chevron" />
          </button>
        ) : null}

        {open && messages.length > 0 ? (
          <ol className="dock__history">
            {messages.map((message) => (
              <li key={message.message_id}>
                <p className="dock__q">{message.question}</p>
                {message.answer ? (
                  <>
                    <p className="dock__a">{message.answer.answer}</p>
                    {/* Labelled, never hidden: a reader has to be able to tell "the review
                        says this" from "the model thinks this". */}
                    {(message.answer.supporting_references || []).length > 0 ? (
                      <p className="dock__grounding">
                        Grounded on {(message.answer.supporting_references || []).join(", ")}
                      </p>
                    ) : (
                      <p className="dock__grounding dock__grounding--none">
                        Not grounded on any reviewed boundary
                      </p>
                    )}
                  </>
                ) : (
                  <p className="dock__failed">{message.failure}</p>
                )}
              </li>
            ))}
          </ol>
        ) : null}

        <form
          className="dock__form"
          onSubmit={(event) => {
            event.preventDefault();
            if (question.trim()) ask.mutate(question.trim());
          }}
        >
          <input
            type="text"
            className="dock__input"
            placeholder="Ask about this review…"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onFocus={() => messages.length > 0 && setOpen(true)}
            disabled={ask.isPending}
            aria-label="Question about this review"
          />
          <button
            type="submit"
            className="button button--primary"
            disabled={ask.isPending || !question.trim()}
          >
            {ask.isPending ? (
              "Thinking…"
            ) : (
              <>
                Ask <CornerDownLeft size={14} aria-hidden />
              </>
            )}
          </button>
        </form>
        {ask.isError ? <ErrorPanel error={ask.error} /> : null}
      </div>
    </div>
  );
}
