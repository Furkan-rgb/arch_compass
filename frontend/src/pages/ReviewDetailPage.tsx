import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  CircleCheck,
  CornerDownLeft,
  FlaskConical,
  MessageCircleQuestion,
  PencilLine,
  Plus,
  TriangleAlert,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import { CaseForm, casePayload, type CaseFormValues } from "../case-form";
import { ErrorPanel, Loading, formatDate, shortId } from "../components";
import { applyProgress, type RunState } from "../run-progress";
import type { ReviewOverview, ReviewScore, ReviewedBoundary } from "../types";

/**
 * One boundary, as a block within a section rather than a card inside a card.
 *
 * The verdict is carried by a left rail rather than by a border and a background, so a
 * cleared boundary reads with the same weight as a material one. It is the record that the
 * advisor looked, and demoting it would make the page identical whether every boundary was
 * examined and cleared or none ever was.
 */
/**
 * The boundaries a claim rests on, as links into the findings themselves.
 *
 * The single most useful move on this page: a reader who doubts a theme is one click from
 * the verdicts it was built from. `:target` highlights the finding on arrival, so the jump
 * is visible without any script deciding what "selected" means.
 */
function Citations({ references }: { references: string[] }) {
  return (
    <span className="cites">
      {references.map((reference) => (
        <a key={reference} className="cite" href={`#${reference}`}>
          {reference}
        </a>
      ))}
    </span>
  );
}

/**
 * What the verdicts amount to, read as a set — the first thing on the page.
 *
 * Leads with the situation because a reader needs to know what this repository is being
 * asked to do before any verdict means anything, and closes with the limits because a
 * reader who has just been told what to do is exactly who needs to know what was not
 * examined.
 */
function Overview({ overview }: { overview: ReviewOverview }) {
  const themes = overview.themes || [];
  const sequence = overview.recommended_sequence || [];
  return (
    <section className="overview" aria-label="What this review amounts to">
      <h2 className="overview__title">What this amounts to</h2>
      <p className="overview__lead">{overview.situation}</p>

      {themes.length > 0 ? (
        <div className="overview__group">
          <h3>Across the boundaries</h3>
          <ul className="overview__list">
            {themes.map((statement) => (
              <li key={statement.text}>
                <span>{statement.text}</span>
                <Citations references={statement.supporting_references || []} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {sequence.length > 0 ? (
        <div className="overview__group">
          <h3>Do this, in order</h3>
          <ol className="overview__list overview__list--ordered">
            {sequence.map((statement) => (
              <li key={statement.text}>
                <span>{statement.text}</span>
                <Citations references={statement.supporting_references || []} />
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {/* Kept even when there is nothing else: "no theme ran across these boundaries" is a
          result, and a reader still has to know what the method could not see. */}
      <p className="overview__limits">
        <strong>What this review could not see.</strong> {overview.limits}
      </p>
    </section>
  );
}

function Finding({ item, policyCount }: { item: ReviewedBoundary; policyCount: number }) {
  const bearings = item.policy_bearings || [];
  const abstraction = item.candidate.participants[0];
  const implementation = item.candidate.participants[1];
  return (
    <article
      id={item.reference}
      className={`finding finding--${item.material ? "material" : "cleared"}`}
    >
      <header className="finding__head">
        <code className="finding__ref">{item.reference}</code>
        <h3 className="finding__title">{abstraction?.qualified_name}</h3>
        {/* The verdict in words, not only as a coloured rail: a reader scanning for "what
            was the answer" should not have to learn a colour convention first. */}
        <span className={`verdict verdict--${item.material ? "material" : "cleared"}`}>
          {item.material ? "Should change" : "Earning its place"}
        </span>
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
        // Open, not collapsed. The substantiation is the reason to believe the verdict, and
        // a reader should not have to go looking for it. The denominator is named on
        // purpose: every policy was presented to every boundary, so one that does not
        // appear here was considered and found not to apply — a different statement from
        // never having been shown.
        <div className="finding__policies">
          <p className="finding__policies-head">
            {bearings.length} of {policyCount} policies bear on this boundary
          </p>
          <ul>
            {bearings.map((bearing) => (
              <li key={bearing.policy_id}>
                <strong>{bearing.policy_title}</strong> {bearing.how}
              </li>
            ))}
          </ul>
        </div>
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
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [open, setOpen] = useState(false);
  const [revising, setRevising] = useState(false);
  const [progress, setProgress] = useState<RunState>(null);

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

  const caseId = review.data?.case_id;
  const caseRevision = review.data?.case_revision;
  const atlasVersionId = review.data?.atlas_version_id;

  /**
   * Every review of this case, so this one can point at its neighbours. Derived from the
   * listing rather than stored on the review: a link recorded at creation time would be a
   * second copy of the same fact, and the earlier review would have to be edited to hold
   * it — which reviews do not permit.
   */
  const siblings = useQuery({
    queryKey: ["reviews", caseId],
    queryFn: () => api.reviews(caseId),
    enabled: Boolean(caseId),
  });

  /** The pinned revision, not the latest: the case this review actually judged against. */
  const pinnedCase = useQuery({
    queryKey: ["case", caseId, caseRevision],
    queryFn: () => api.case(caseId!, caseRevision),
    enabled: Boolean(caseId && caseRevision),
  });

  // The atlas the review pinned answers where the repository is; a review carries the
  // version, and the listing is what turns a version into a path.
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const repositoryRoot =
    repositories.data?.find((item) => item.version_id === atlasVersionId)?.root_path ||
    pinnedCase.data?.snapshot?.repository?.root_path ||
    null;

  /**
   * Which thread is being read. Threads are durable and there may be many, so the newest is
   * shown by default and the rest stay reachable. `"new"` means the next question starts a
   * thread: an empty conversation is a record that then has to be explained in a listing, so
   * one is created when there is finally something to put in it.
   */
  const threads = conversations.data || [];
  const [threadId, setThreadId] = useState<string | "new" | null>(null);
  const conversation =
    threadId === "new"
      ? undefined
      : threads.find((item) => item.conversation_id === threadId) || threads[0];
  const messages = conversation?.messages || [];

  // The listing is newest first, so the review before this one in it is the newer one.
  const ordered = siblings.data || [];
  const position = ordered.findIndex((item) => item.review_id === reviewId);
  const newer = position > 0 ? ordered[position - 1] : null;
  const earlier = position >= 0 ? ordered[position + 1] || null : null;

  const revise = useMutation({
    mutationFn: async (values: CaseFormValues) => {
      if (!caseId || !repositoryRoot) {
        throw new Error("This review's case and repository could not both be resolved.");
      }
      setProgress(null);
      // Two steps, deliberately in this order and never in place: a new immutable case
      // revision, then a new review of it. This review is not touched by either.
      await api.updateCase(caseId, casePayload(values));
      return api.streamReview(caseId, repositoryRoot, (event) =>
        setProgress((current) => applyProgress(current, event)),
      );
    },
    onSuccess: async (next) => {
      setRevising(false);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["reviews"] }),
        client.invalidateQueries({ queryKey: ["cases"] }),
      ]);
      navigate(`/reviews/${next.review_id}`);
    },
  });

  const ask = useMutation({
    mutationFn: async (text: string) => {
      // Created on first use rather than alongside the review: a conversation with no
      // questions in it is an empty record that then has to be explained in a listing.
      const target = conversation ?? (await api.createReviewConversation(reviewId));
      if (!target.conversation_id) {
        throw new Error("The workspace returned a conversation without an identifier.");
      }
      return { message: await api.askReviewQuestion(target.conversation_id, text), target };
    },
    onSuccess: async ({ target }) => {
      setQuestion("");
      setOpen(true);
      // A question asked into a new thread lands in that thread, not back in the newest.
      setThreadId(target.conversation_id || null);
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
        {/* What this review is pinned to. Already in the record; printed rather than
            implied, because "which case revision said so" is the first question a second
            reading asks. */}
        <dl className="provenance">
          <div>
            <dt>Case revision</dt>
            <dd>
              {pinnedCase.data?.snapshot?.title || report.case_title} · rev{" "}
              {review.data?.case_revision}
            </dd>
          </div>
          <div>
            <dt>Atlas version</dt>
            <dd title={atlasVersionId}>{shortId(atlasVersionId || "—")}</dd>
          </div>
          <div>
            <dt>Policies presented</dt>
            <dd>{policyCount}, whole corpus, to every boundary</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd title={review.data?.prompt_identity}>{review.data?.reasoning_model}</dd>
          </div>
          <div>
            <dt>Reviewed</dt>
            <dd>{formatDate(review.data?.created_at)}</dd>
          </div>
        </dl>

        <div className="review-head__actions">
          <button
            type="button"
            className="button button--primary"
            disabled={revise.isPending || !repositoryRoot}
            title={
              repositoryRoot
                ? undefined
                : "The repository this review ran against is no longer indexed."
            }
            onClick={() => setRevising((value) => !value)}
          >
            <PencilLine size={15} aria-hidden /> Revise case &amp; review again
          </button>
          {ordered.length > 1 ? (
            <nav className="review-siblings" aria-label="Other reviews of this case">
              {earlier ? (
                <Link to={`/reviews/${earlier.review_id}`}>
                  <ArrowLeft size={14} aria-hidden /> Earlier review · case rev{" "}
                  {earlier.case_revision}
                </Link>
              ) : null}
              <span>
                {position + 1} of {ordered.length} reviews of this case
              </span>
              {newer ? (
                <Link to={`/reviews/${newer.review_id}`}>
                  Newer review · case rev {newer.case_revision}{" "}
                  <ArrowRight size={14} aria-hidden />
                </Link>
              ) : null}
            </nav>
          ) : null}
        </div>
      </header>

      {revising ? (
        <CaseForm
          // Keyed by the pinned revision so the form mounts with that revision's answers,
          // not with the empty defaults it was first built from.
          key={`${caseId}:${caseRevision}`}
          heading="Revise the case, then review again"
          initial={pinnedCase.data?.snapshot}
          submitLabel="Create revision &amp; review again"
          pendingLabel="Reviewing…"
          pending={revise.isPending}
          loading={pinnedCase.isLoading}
          error={pinnedCase.error || revise.error}
          progress={progress}
          onSubmit={(values) => revise.mutate(values)}
          onClose={() => setRevising(false)}
          note={
            <p className="case-editor__warning">
              <strong>This does not change the review you are reading.</strong> Submitting
              creates revision {(caseRevision ?? 0) + 1} of the case and runs a new review
              against the same atlas, so only the case has changed. Both reviews stay, and
              each links to the other.
            </p>
          }
        />
      ) : null}

      <Overview overview={report.overview} />

      {score.data ? <Score score={score.data} /> : null}

      <p className="boundaries-note">
        Every boundary examined is below, cleared ones included. <code>BR-001</code> and the
        rest are references ArchCompass assigns in detection order — the citations above lead
        to them, and citing one in a question makes the answer cite it back.
      </p>

      {material.length > 0 ? (
        <section className="group">
          <h2 className="group__title">
            <TriangleAlert size={16} aria-hidden /> Should change
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

        {/* Threads are durable, so they are worth returning to. Each is labelled by its
            first question rather than by its title: every thread on one review would
            otherwise carry the same generated name. */}
        {threads.length > 0 || threadId === "new" ? (
          <div className="dock__threads" role="group" aria-label="Question threads">
            {/* Oldest first, though the listing arrives newest first: a thread should not
                move along the row every time another one is started. The newest is still
                what opens by default — that is the one you came back to. */}
            {[...threads].reverse().map((thread) => (
              <button
                key={thread.conversation_id}
                type="button"
                aria-pressed={conversation?.conversation_id === thread.conversation_id}
                className={
                  conversation?.conversation_id === thread.conversation_id ? "is-active" : ""
                }
                onClick={() => {
                  setThreadId(thread.conversation_id || null);
                  setOpen(true);
                }}
                title={thread.messages?.[0]?.question || thread.title}
              >
                <span>{thread.messages?.[0]?.question || thread.title}</span>
              </button>
            ))}
            <button
              type="button"
              aria-pressed={threadId === "new"}
              className={threadId === "new" ? "is-active" : ""}
              onClick={() => {
                setThreadId("new");
                setOpen(false);
              }}
            >
              <Plus size={13} aria-hidden /> New thread
            </button>
          </div>
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
