import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  CircleCheck,
  CornerDownLeft,
  FlaskConical,
  MessageCircleQuestion,
  Network,
  PencilLine,
  Plus,
  TriangleAlert,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { CaseForm, casePayload, type CaseFormValues } from "../case-form";
import { Markdown } from "../markdown";
import { ErrorPanel, Loading, formatDate, shortId } from "../components";
import { ReviewAtlas } from "../review-atlas";
import { ReviewInProgress } from "../review-in-progress";
import { useRun } from "../run";
import type {
  BoundaryReview,
  ReviewOverview,
  ReviewScore,
  ReviewedBoundary,
} from "../types";

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
/**
 * An answer as the model wrote it: prose, with code shown as code.
 *
 * The same renderer the Policies page uses, so a fenced block, a table or a bulleted list
 * reads the same wherever it appears. It also matters more here than there — an answer about
 * a boundary routinely shows the two-line change it is describing, and a diff rendered as one
 * run-on paragraph is worse than no example at all.
 *
 * Safe to call on a partial answer. An unclosed fence is treated as a code block running to
 * the end of what has arrived, which is exactly right for a block still being written; it is
 * highlighted from the first line rather than turning colour once the answer finishes.
 */
export function AnswerProse({ text }: { text: string }) {
  return (
    <div className="markdown dock__a">
      <Markdown>{text}</Markdown>
    </div>
  );
}

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
 * Leads with the bottom line — the situation, what came out wrong, and what to do — because
 * a reader who gets no further than the first sentence should still know where they stand.
 * Closes with the limits, because a reader who has just been told what to do is exactly who
 * needs to know what was not examined.
 */
export function Overview({
  overview,
  onAnswer,
}: {
  overview: ReviewOverview;
  // Opens the case editor this page already carries. The answer path is the revise-and-
  // review loop that exists, not a second way to write a case: a question names a field
  // and the reader fills it in, so what the advisor supplies is the question and what
  // enters the case is the user's own revision (master plan §6C.4).
  onAnswer?: (() => void) | null;
}) {
  const themes = overview.themes || [];
  const sequence = overview.recommended_sequence || [];
  const questions = overview.open_questions || [];
  return (
    // "Conclusion", not "Findings": the findings are the boundaries below, each with its
    // own verdict. This is the one thing none of those separate calls could produce — what
    // they amount to read as a set.
    <section className="overview" aria-label="Conclusion">
      <h2 className="overview__title">Conclusion</h2>
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
          <h3>Recommended actions, in order</h3>
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

      {/* Last, and only when there is something to ask. A review that opens by asking for
          more information has put its price before its value, which is the adoption tax
          elicitation exists to remove — so the questions come after the answer, addressed
          to a reader who has already seen what the review is worth. */}
      {questions.length > 0 ? (
        <div className="overview__group questions">
          <h3>What the case does not say</h3>
          <p className="questions__lead">
            Each of these would settle verdicts above. Answering one is a case revision, and
            a new review against it can reach a different verdict.
          </p>
          <ol className="questions__list">
            {questions.map((item) => (
              <li key={item.reference} className="question">
                <p className="question__ask">
                  <code className="question__ref">{item.reference}</code>
                  {item.question}
                </p>
                <p className="question__unknown">{item.unknown}</p>
                <p className="question__why">
                  <span>{item.why_it_matters}</span>
                  <Citations references={item.supporting_references || []} />
                </p>
                <p className="question__target">
                  An answer belongs in <code>{item.answer_belongs_in}</code>
                  {onAnswer ? (
                    <button type="button" className="question__answer" onClick={onAnswer}>
                      Answer it in the case
                    </button>
                  ) : null}
                </p>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}

function Finding({
  item,
  policyCount,
  onShowInAtlas,
}: {
  item: ReviewedBoundary;
  policyCount: number;
  onShowInAtlas: ((nodeId: string) => void) | null;
}) {
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
            was the answer" should not have to learn a colour convention first. The wording
            comes from the review rather than from here, because it depends on which shape
            was judged — "not earning its place" is right for indirection that hides nothing
            and wrong for a constant copied into four modules. */}
        <span className={`verdict verdict--${item.material ? "material" : "cleared"}`}>
          {item.verdict_label}
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
          <strong>Recommendation.</strong> {item.recommended_response}
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
          {/* A card each, three across, each only as tall as its own sentence. As a
              bulleted list the policy's name and the sentence explaining how it bears ran
              together into one paragraph, and a reader could not tell where one policy
              stopped and the next began. */}
          <ul className="bearings">
            {bearings.map((bearing) => (
              <li key={bearing.policy_id} className="bearing">
                <strong className="bearing__title">{bearing.policy_title}</strong>
                <span className="bearing__how">{bearing.how}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="finding__policies finding__policies--none">
          None of the {policyCount} policies presented bore on this boundary.
        </p>
      )}

      {/* What the case did not say, beside what the method could not see. Two different
          things a verdict rests on, and only this one is the reader's to fix — which is why
          it sits above the limits rather than being folded into them. */}
      {item.hinge ? (
        <p className="finding__hinge">
          <strong>This verdict turns on an open question.</strong> {item.hinge.unknown}{" "}
          <span className="finding__hinge-branch">If so: {item.hinge.if_confirmed}</span>{" "}
          <span className="finding__hinge-branch">If not: {item.hinge.if_denied}</span>
        </p>
      ) : null}

      <p className="finding__limits">{item.candidate.limitations}</p>

      {/* The map this finding raises a question about is further down the same page, so
          this moves the reader to it rather than opening a second place to be. Leaving the
          review to answer "where does this sit" lost the review; the question and its
          answer belong in one reading (workspace-design §4). Absent when the atlas is no
          longer indexed and there is nothing below to scroll to. */}
      {onShowInAtlas && abstraction?.node_id ? (
        <button
          type="button"
          className="finding__atlas"
          onClick={() => onShowInAtlas(abstraction.node_id)}
        >
          <Network size={14} aria-hidden /> Show {item.reference} in the atlas
        </button>
      ) : null}
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
              {item.actual ? "should change" : "fine as it is"}
              {item.correct
                ? ""
                : ` — expected ${item.expected ? "should change" : "fine as it is"}`}
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

/**
 * A review that ended without a judgement: cancelled, or failed.
 *
 * Not an error page. The row exists from the moment the run starts, so this is what a review
 * page looks like when the run ended and no subject ever will exist. A run still going is a
 * different thing entirely and has its own component; this one is the aftermath.
 */
function Unfinished({ review }: { review: BoundaryReview }) {
  const cancelled = review.status === "cancelled";
  return (
    <div className="page page--review">
      <header className="review-head">
        <span className="eyebrow">Boundary review</span>
        <h1>{cancelled ? "This review was cancelled" : "This review did not finish"}</h1>
        <p className="review-head__meta">
          Case <code>{shortId(review.case_id)}</code> · revision {review.case_revision} ·
          started {formatDate(review.created_at)}
        </p>
      </header>
      <div className="unfinished">
        {/* Cancelling records no reason, because there is none to record beyond the choice
            itself. Only what ArchCompass wrote for a person to read reaches this list; an
            unexpected failure is recorded without its text. */}
        {cancelled ? (
          <p className="unfinished__note">
            It stopped after the boundary it was judging at the time. The verdicts it had
            already reached were not kept: a review is every boundary or none, and half of
            one would read as a complete answer.
          </p>
        ) : (
          <ul className="unfinished__errors">
            {(review.sanitized_errors || []).map((message) => (
              <li key={message}>{message}</li>
            ))}
            {(review.sanitized_errors || []).length === 0 ? (
              <li>No reason was recorded.</li>
            ) : null}
          </ul>
        )}
        <p className="unfinished__note">
          Nothing was written to the case or the atlas. A review is derived from both, so
          running it again is the whole of the fix. <Link to="/">Start a review</Link> ·{" "}
          <Link to="/reviews">All reviews</Link>
        </p>
      </div>
    </div>
  );
}

export function ReviewDetailPage() {
  const { reviewId = "" } = useParams();
  const client = useQueryClient();
  const [question, setQuestion] = useState("");
  const [open, setOpen] = useState(false);
  /**
   * The question being answered right now, and the prose that has arrived for it.
   *
   * Held apart from the thread's messages on purpose: those are the record, and this is text
   * on its way to being validated. Nothing here is grounded — citations come from flags that
   * do not exist until the whole reply has arrived — so it is labelled as still being written
   * rather than shown as an answer the review supports.
   */
  const [pending, setPending] = useState<{
    question: string;
    prose: string;
  } | null>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const slotRef = useRef<HTMLDivElement>(null);
  const contentEnd = useRef<HTMLDivElement>(null);
  const [revising, setRevising] = useState(false);
  // The map is one section of this page, so which node it shows is the page's state: a
  // finding above can ask for its own boundary, and the two must not each hold an answer.
  const [atlasNodeId, setAtlasNodeId] = useState<string | null>(null);
  const atlasRef = useRef<HTMLElement>(null);
  const run = useRun();

  const review = useQuery({
    queryKey: ["review", reviewId],
    queryFn: () => api.review(reviewId),
    enabled: Boolean(reviewId),
    // A review opened while it is still being produced is a page waiting for its own
    // subject. It polls until the run ends and then stops: the review is immutable
    // afterwards, so there is nothing further to ask about.
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });
  const score = useQuery({
    queryKey: ["review-score", reviewId],
    queryFn: () => api.reviewScore(reviewId),
    // Only once there is a judgement to grade. The page is now open while the review is
    // still being produced, and a score asked for then answers "no score" truthfully — an
    // answer that would then be cached over the real one.
    enabled: Boolean(reviewId) && review.data?.status === "succeeded",
  });
  const conversations = useQuery({
    queryKey: ["review-conversations", reviewId],
    queryFn: () => api.reviewConversations(reviewId),
    enabled: Boolean(reviewId),
  });

  /**
   * How tall the dock may be: its reserved slot while there is page left to read, and up to
   * the whole screen once the reader has reached the end of it.
   *
   * How far from the end the reader is comes from two element positions and never from
   * `scrollHeight`. With a sticky element on the page those disagree: Chromium reports a
   * scroll height a couple of hundred pixels larger than the furthest the page will actually
   * scroll, so a page scrolled fully to the bottom looks like it still has some way to go and
   * the dock never expands at all. `marker` sits in the flow just above the slot, so its
   * distance from the viewport's bottom edge is a fact about the content and is exact.
   *
   * That the slot reserves a fixed space is what makes the measurement stable. In the flow the
   * dock's own height moved the end of the page, so the answer to "am I at the end" changed as
   * a result of acting on it — the loop that made the dock feel stuck between its two sizes.
   * Nothing here can change what it measures.
   *
   * The two thresholds are hysteresis, and they are the second half of the robustness: forty
   * pixels from the end to expand, a hundred and sixty to collapse again. The gap is what stops
   * the boundary being a knife edge — a trackpad settling short of the end, or the atlas
   * finishing its layout and moving things by a few pixels, would otherwise leave the dock
   * flipping between its two sizes. The entry threshold is deliberately forgiving: there is
   * nothing below the dock to cover, so being near the end is as good as being at it.
   *
   * Written straight onto the node rather than held in state. Scroll-driven styling routed
   * through React re-renders the page on every frame of a scroll, and what it computes is a
   * presentational value nothing else reads.
   */
  const status = review.data?.status;
  useEffect(() => {
    if (!dockRef.current) return;
    let frame = 0;
    let expanded = false;
    const measure = () => {
      frame = 0;
      const dock = dockRef.current;
      const marker = contentEnd.current;
      const slot = slotRef.current;
      if (!dock || !marker || !slot) return;
      // At the very end of the page the marker sits exactly one slot's height above the
      // bottom of the screen, because the slot is the last thing in the flow. Anything more
      // than that is page still to come.
      const fromEnd =
        marker.getBoundingClientRect().top +
        slot.getBoundingClientRect().height -
        window.innerHeight;
      expanded = fromEnd <= (expanded ? 160 : 40);
      dock.style.setProperty("--dock-max", expanded ? "100vh" : "20vh");
    };
    // Coalesced to one measurement per frame: scroll fires far more often than the screen is
    // painted, and each measurement reads layout.
    const schedule = () => {
      frame ||= requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    // The page changes height without anyone scrolling — the atlas finishes loading, an answer
    // arrives — and where the end of it is moves with that.
    const resized = new ResizeObserver(schedule);
    resized.observe(document.body);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      resized.disconnect();
    };
  }, [status]);

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
    // The listing is also where a running review's counts live — the review document has
    // no room for how far it has got — so it follows the run while there is one.
    refetchInterval: () => (review.data?.status === "running" ? 2000 : false),
  });

  /** The pinned revision, not the latest: the case this review actually judged against. */
  const pinnedCase = useQuery({
    queryKey: ["case", caseId, caseRevision],
    queryFn: () => api.case(caseId!, caseRevision),
    enabled: Boolean(caseId && caseRevision),
  });

  // The atlas the review pinned answers where the repository is; a review carries the
  // version, and the listing is what turns a version into a path.
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: api.repositories,
  });
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

  /**
   * Keep the newest exchange in view inside the history's own scroller.
   *
   * The list runs oldest to newest and the window onto it is now small, so without this a new
   * answer lands below the fold of that window and the reader is left looking at a question
   * they asked three turns ago. It follows the arriving prose too, so a streamed answer stays
   * visible as it is written rather than growing downwards out of sight.
   */
  const historyRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const list = historyRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length, pending?.prose, open]);

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
      // Two steps, deliberately in this order and never in place: a new immutable case
      // revision, then a new review of it. This review is not touched by either.
      await api.updateCase(caseId, casePayload(values));
      // Handed to the run, which takes the reader to the new review as soon as it has an
      // identity — the same path the start step takes, so there is one place a run is
      // watched however it was started.
      run.start(caseId, repositoryRoot);
    },
    onSuccess: async () => {
      setRevising(false);
      await client.invalidateQueries({ queryKey: ["cases"] });
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
      // Streamed, so the answer reads as it is written. `pending` is only ever what the
      // fragments have built — never the record — and is dropped the moment the appended
      // message arrives, which is what a re-read of this thread will show.
      setPending({ question: text, prose: "" });
      const message = await api.streamReviewQuestion(
        target.conversation_id,
        text,
        (fragment) =>
          setPending((current) =>
            current ? { ...current, prose: current.prose + fragment } : current,
          ),
      );
      return { message, target };
    },
    onSuccess: async ({ target }) => {
      setQuestion("");
      setOpen(true);
      // A question asked into a new thread lands in that thread, not back in the newest.
      setThreadId(target.conversation_id || null);
      await client.invalidateQueries({
        queryKey: ["review-conversations", reviewId],
      });
      // Cleared after the history has been refetched, so the answer never blinks out of
      // existence between the preview going and the stored message arriving.
      setPending(null);
    },
    // A failed turn is appended as a failure, so the history below is where it shows. The
    // half-written prose goes: it was on its way to being checked and did not pass.
    onError: () => setPending(null),
  });

  if (review.isLoading) return <Loading label="Reading the review…" />;
  if (review.isError) return <ErrorPanel error={review.error} />;

  // The row exists from the moment the run starts, so this page has to be able to show a
  // review that is not finished — and a run in progress is one component, used here and
  // nowhere else, whether this tab is the one producing it or not.
  if (review.data?.status === "running") {
    return (
      <ReviewInProgress
        review={review.data}
        summary={siblings.data?.find((item) => item.review_id === reviewId)}
        live={run.watching(reviewId) ? run.progress : undefined}
        watching={run.watching(reviewId)}
        title={pinnedCase.data?.snapshot?.title || null}
      />
    );
  }
  if (review.data && review.data.status !== "succeeded") {
    return <Unfinished review={review.data} />;
  }
  const report = review.data?.report;
  if (!report) {
    return <ErrorPanel error={new Error("This review did not produce a report.")} />;
  }

  const reviewed = report.reviewed || [];
  const policyCount = (report.policies_presented || []).length;
  const material = reviewed.filter((item) => item.material);
  const cleared = reviewed.filter((item) => !item.material);

  // Only when there is a map below to be shown in. Selecting first and scrolling second so
  // the node is already the selected one when the section arrives, rather than settling
  // into place and then changing under the reader.
  const showInAtlas =
    repositoryRoot && reviewed.length > 0
      ? (nodeId: string) => {
          setAtlasNodeId(nodeId);
          atlasRef.current?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }
      : null;

  return (
    <div className="page page--review">
      <header className="review-head">
        <span className="eyebrow">Boundary review</span>
        <h1>{report.case_title}</h1>
        <p className="review-head__meta">
          <strong>{reviewed.length}</strong> boundaries examined ·{" "}
          <strong>{policyCount}</strong> policies presented to each ·{" "}
          <strong>{material.length}</strong> should change,{" "}
          <strong>{cleared.length}</strong> left as they are
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
          // Keyed by what has actually loaded, not by what was asked for: the review knows
          // its case and revision immediately, so keying on those alone would hold the key
          // steady while the answers were still arriving and mount the form empty.
          key={`${caseId}:${pinnedCase.data?.revision ?? "loading"}`}
          heading="Revise the case, then review again"
          initial={pinnedCase.data?.snapshot}
          submitLabel="Create revision &amp; review again"
          pendingLabel="Reviewing…"
          pending={revise.isPending}
          loading={pinnedCase.isLoading}
          error={pinnedCase.error || revise.error}
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

      {/* The answer path is offered only where it can actually be walked: revising runs a
          new review, which needs the repository still indexed. A question with a button
          that fails is worse than one that leaves the reader to the case editor above. */}
      <Overview
        overview={report.overview}
        onAnswer={repositoryRoot ? () => setRevising(true) : null}
      />

      {score.data ? <Score score={score.data} /> : null}

      <p className="boundaries-note">
        Every boundary examined is below, cleared ones included. <code>BR-001</code> and the
        rest are references ArchCompass assigns in detection order — the citations above
        lead to them, and citing one in a question makes the answer cite it back.
      </p>

      {material.length > 0 ? (
        <section className="group">
          <h2 className="group__title">
            <TriangleAlert size={16} aria-hidden /> What should change
            <span className="group__count">{material.length}</span>
          </h2>
          {/* Shape-neutral, because these are grouped by verdict and the group can hold
              both directions of the catalogue at once: indirection that hides nothing, and
              knowledge with no owner. Each finding names its own shape on its own badge. */}
          <p className="group__hint">
            Each of these was found to cost more than it earns under this case.
          </p>
          {material.map((item) => (
            <Finding
              key={item.reference}
              item={item}
              policyCount={policyCount}
              onShowInAtlas={showInAtlas}
            />
          ))}
        </section>
      ) : null}

      {cleared.length > 0 ? (
        <section className="group">
          <h2 className="group__title">
            <CircleCheck size={16} aria-hidden /> Examined and left alone
            <span className="group__count">{cleared.length}</span>
          </h2>
          <p className="group__hint">
            The advisor examined each of these and concluded it should stay as it is.
          </p>
          {cleared.map((item) => (
            <Finding
              key={item.reference}
              item={item}
              policyCount={policyCount}
              onShowInAtlas={showInAtlas}
            />
          ))}
        </section>
      ) : null}

      {/* After the verdicts, not before them. The map answers "where does this sit", which
          is a question a reader has only once they know what was decided; above the
          findings it would push every verdict below the fold to make room for context
          nobody had asked for yet. */}
      {repositoryRoot && reviewed.length > 0 ? (
        <ReviewAtlas
          repositoryRoot={repositoryRoot}
          boundaries={reviewed}
          selectedNodeId={atlasNodeId}
          onSelectNode={setAtlasNodeId}
          sectionRef={atlasRef}
        />
      ) : null}

      {/*
        The slot is what sits in the page — a fixed 20vh, sticky to the bottom of the viewport
        while there is page left below it, settling into its own place at the end. The dock is
        positioned inside it and may be taller than it, which is what keeps the document's
        height independent of the conversation's length. See `.dock-slot` and the effect above.
      */}
      <div ref={contentEnd} className="dock__anchor" aria-hidden />
      <div ref={slotRef} className="dock-slot">
        <div ref={dockRef} className={`dock ${open ? "dock--open" : ""}`}>
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
                    conversation?.conversation_id === thread.conversation_id
                      ? "is-active"
                      : ""
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

          {open || pending ? (
            <ol className="dock__history" ref={historyRef}>
              {messages.map((message) => (
                <li key={message.message_id}>
                  <p className="dock__q">{message.question}</p>
                  {message.answer ? (
                    <>
                      <AnswerProse text={message.answer.answer} />
                      {/* Labelled, never hidden: a reader has to be able to tell "the review
                        says this" from "the model thinks this". */}
                      {(message.answer.supporting_references || []).length > 0 ? (
                        <p className="dock__grounding">
                          Grounded on{" "}
                          {(message.answer.supporting_references || []).join(", ")}
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
              {/* The turn in flight. `aria-live` so the answer is read as it arrives rather
                than announced once at the end; `aria-busy` so a screen reader is told this
                is unfinished, which is the same thing the caption below says in text. */}
              {pending ? (
                <li className="dock__pending" aria-live="polite" aria-busy="true">
                  <p className="dock__q">{pending.question}</p>
                  {pending.prose ? (
                    <>
                      <AnswerProse text={pending.prose} />
                      {/* Not "not grounded" — nothing is settled yet, and a grounding line
                        here would be a claim about an answer that is still being written. */}
                      <p className="dock__grounding dock__grounding--pending">
                        Still being written
                      </p>
                    </>
                  ) : (
                    <p className="dock__grounding dock__grounding--pending">Thinking…</p>
                  )}
                </li>
              ) : null}
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
    </div>
  );
}
