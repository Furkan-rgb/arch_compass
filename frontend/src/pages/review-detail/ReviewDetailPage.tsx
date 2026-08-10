/**
 * One review, whole: what it read, what it judged, what it still needs asked, and the map it
 * judged against. This file is the shell — the queries the page runs, the state the tabs
 * share, and the order things appear in. Each tab and each band lives in its own file beside
 * this one.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import { api } from "../../api";
import { AskPanel } from "../../ask-panel";
import { Loading, PageHeader, page, sheet, shortId } from "../../components";
import { ask } from "../../review-capabilities";
import { HoldBanner } from "../../review-awaiting";
import { watchedProgress } from "../../review-in-progress";
import { VerdictBand } from "../../review-ledger";
import { useRun } from "../../run";
import { type SubmittedAnswer } from "../../review-questions";
import { AtlasTab, findingForNode } from "./atlas-tab";
import { FindingsTab } from "./findings-tab";
import { AskAction, ExportAction } from "./header-actions";
import { PassesRail } from "./passes-rail";
import { QuestionsTab } from "./questions-tab";
import { ReviewUnavailable, ReviewUnfinished } from "./review-dead-ends";
import { RevisionStrip } from "./revision-strip";
import { RunLogTab } from "./run-log-tab";
import { chainAround } from "./review-chain";
import { verdictFacts } from "./verdict-facts";
import type { BoundaryTriage } from "../../types";

type TabId = "findings" | "questions" | "runlog" | "atlas";

export function ReviewDetailPage() {
  const { reviewId = "" } = useParams();
  const client = useQueryClient();
  const [tab, setTab] = useState<TabId>("findings");
  /**
   * Which tabs have been opened. A panel is mounted on first visit and kept mounted after,
   * so the atlas does not re-inspect every boundary each time the reader comes back to it —
   * and does not inspect any of them on a visit that never opens the map.
   */
  const [visited, setVisited] = useState<TabId[]>(["findings"]);
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  // The map is one tab of this page, so which node it shows is the page's state: a finding
  // can ask for its own boundary, and the two must not each hold an answer.
  const [atlasNodeId, setAtlasNodeId] = useState<string | null>(null);
  /**
   * Which review these all belong to.
   *
   * The route keeps this component mounted when the reader moves from one review to
   * another — answering navigates from a first pass to the second it started — so without
   * this the new review opens on whichever tab the old one was left on, with a row expanded
   * that its ledger does not contain.
   */
  const [shown, setShown] = useState(reviewId);
  if (shown !== reviewId) {
    setShown(reviewId);
    setTab("findings");
    setVisited(["findings"]);
    setOpenRow(null);
    setAtlasNodeId(null);
    // A panel is about one review, so it does not follow the reader to the next one —
    // answering a held review navigates straight from that pass to the one it starts.
    setAsking(false);
  }
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

  const caseId = review.data?.case_id;
  const caseRevision = review.data?.case_revision;
  const atlasVersionId = review.data?.atlas_version_id;

  /**
   * The listing entry for this review, which is where a running review's counts live — the
   * review document has no room for how far it has got.
   *
   * It also feeds the passes rail: the case's other reviews carry the `elicited_from`
   * links, and the rail is the walk along them. It once fed arrows that navigated by case
   * revision instead, which landed readers on the in-progress screen of a pass that was
   * never run — the rail names each pass by what it did, which is the difference.
   */
  const siblings = useQuery({
    queryKey: ["reviews", caseId],
    queryFn: () => api.reviews(caseId),
    enabled: Boolean(caseId),
    refetchInterval: () => (review.data?.status === "running" ? 2000 : false),
  });

  /** The pinned revision, not the latest: the case this review actually judged against. */
  const pinnedCase = useQuery({
    queryKey: ["case", caseId, caseRevision],
    queryFn: () => api.case(caseId!, caseRevision),
    enabled: Boolean(caseId && caseRevision),
  });

  /**
   * The first pass this review answers, where there is one.
   *
   * Fetched rather than derived, because what it is needed for is the verdicts themselves —
   * the listing carries counts, and "which verdicts moved" is a comparison per boundary. Only
   * on a second pass, so an ordinary review makes no extra request.
   */
  const elicitedFrom = review.data?.elicited_from ?? null;
  const earlierPass = useQuery({
    queryKey: ["review", elicitedFrom],
    queryFn: () => api.review(elicitedFrom!),
    enabled: Boolean(elicitedFrom),
  });

  /**
   * The review that asked the questions this revision answered, whichever review that was.
   *
   * Not the same thing as the pass this one answers. Only the answers are recorded on the
   * case, by reference — the wording lives on the review that asked — and a third review
   * judging the same answered revision was elicited from nobody. Reading the asking review
   * off the revision itself is what lets it show the questions rather than a placeholder.
   * The same id on a second pass, so react-query serves it from what `earlierPass` fetched.
   */
  const askedBy = pinnedCase.data?.answered?.review_id ?? null;
  const askingPass = useQuery({
    queryKey: ["review", askedBy],
    queryFn: () => api.review(askedBy!),
    enabled: Boolean(askedBy),
  });

  // The atlas the review pinned answers where the repository is; a review carries the
  // version, and the listing is what turns a version into a path.
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: api.repositories,
  });
  // The whole listing and the branch lineages, for the revision strip: which branches of
  // this repository carry a line, and where this review sits on its own.
  const allReviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const branchLineages = useQuery({ queryKey: ["branches"], queryFn: api.branches });
  const indexedAtlas = repositories.data?.find((item) => item.version_id === atlasVersionId);
  const repositoryRoot =
    indexedAtlas?.root_path || pinnedCase.data?.snapshot?.repository?.root_path || null;

  // Answering, in one call. The workspace resolves each `Q-n` against this review's own
  // report, pairs the answer with the question it asked, and records what it answered in the
  // same transaction — which is what makes the link from a case entry back to its question
  // impossible to lose.
  //
  // The new run then names this review as the one it answers, and that is what makes it a
  // second pass: it judges against the answered case and concludes rather than asking again.
  const answer = useMutation({
    mutationFn: async (answers: SubmittedAnswer[]) => {
      if (!caseId || !repositoryRoot) {
        throw new Error("This review's case and repository could not both be resolved.");
      }
      await api.answerReview(reviewId, answers);
      run.start(caseId, repositoryRoot, reviewId);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["cases"] });
    },
  });

  // The next revision of this branch's line: re-index, continue the branch's case, judge
  // the delta. The same start the start step performs, offered where the line lives.
  const newRevision = useMutation({
    mutationFn: async () => {
      if (!repositoryRoot) {
        throw new Error("This review's repository could not be resolved.");
      }
      // A managed checkout is brought current first, so "re-analyse the code" means the
      // repository's code, not whatever the clone last held. Anyone else's working copy
      // comes back managed:false untouched, so this is safe to ask unconditionally.
      await api.refreshRepository(repositoryRoot);
      // No check here: a revision that would move nothing is the run's own first decision,
      // refused inside the service before anything is written, and the run's holder shows
      // the notice wherever the reader is. This handler only starts the run.
      const revision = await api.startFromRepository(repositoryRoot);
      if (!revision.case_id) {
        throw new Error("The workspace returned a case without an identifier.");
      }
      run.start(revision.case_id, repositoryRoot);
    },
  });

  const report = review.data?.report ?? null;
  const reviewed = report?.reviewed || [];
  const branchId = review.data?.branch_id ?? null;
  // Reference → triage join, for the ledger rows. Rebuilt per render from a list that is
  // at most dozens long; a memo here would be bookkeeping for nothing.
  const triageByReference = new Map<string, BoundaryTriage>(
    (review.data?.boundary_triage ?? []).map((entry) => [entry.reference, entry]),
  );

  const references = reviewed.map((item) => item.reference).join(" ");
  // Material with nobody's name on it — what the bulk gesture would decide.
  const undecided = reviewed.filter(
    (item) =>
      item.material &&
      item.fingerprint &&
      !triageByReference.get(item.reference)?.decision,
  );

  /**
   * A citation opens the row it names, in the tab that holds it.
   *
   * `hashchange` rather than the router's location: an anchor pointing at the same document
   * never reaches the router, so a citation clicked in the conclusion would otherwise scroll
   * to a collapsed row and show nothing. Selecting first and scrolling second, so the
   * reasoning is already open when the row arrives rather than unfolding under the reader.
   */
  const openTab = (id: TabId) => {
    setTab(id);
    setVisited((current) => (current.includes(id) ? current : [...current, id]));
  };
  const openTabRef = useRef(openTab);
  openTabRef.current = openTab;
  useEffect(() => {
    const jump = () => {
      const wanted = decodeURIComponent(window.location.hash.slice(1));
      if (!wanted || !references.split(" ").includes(wanted)) return;
      openTabRef.current("findings");
      setOpenRow(wanted);
      requestAnimationFrame(() =>
        document.getElementById(wanted)?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    };
    jump();
    window.addEventListener("hashchange", jump);
    return () => window.removeEventListener("hashchange", jump);
  }, [references]);

  // Both of these are the page, drawn with its subject missing — not something rendered
  // instead of it. A bare strip on the canvas had no header, no column and no width, so the
  // whole layout snapped into place around the reader the moment the review landed.
  if (review.isLoading) {
    return (
      <div data-slot="review-page" className={cn(page, "pb-6")}>
        {/* The id, because it is the whole of what is known about this review before it has
            been read — and because it is also the fallback the loaded page falls back to,
            so a review without a title does not rename its own header on arrival. */}
        <PageHeader title={shortId(reviewId)} parent={{ to: "/reviews", label: "Reviews" }} />
        <div className={sheet}>
          <Loading label="Reading the review…" rows={3} />
        </div>
      </div>
    );
  }
  if (review.isError) {
    return (
      <ReviewUnavailable
        reviewId={reviewId}
        error={review.error}
        onRetry={() => void review.refetch()}
        retrying={review.isFetching}
      />
    );
  }

  const status = review.data?.status;
  // The row exists from the moment the run starts, so this page has to be able to show a
  // review that never reached a judgement. Both of those are aftermaths, not errors.
  if (review.data && status !== "running" && status !== "succeeded" && status !== "awaiting_answers") {
    return <ReviewUnfinished review={review.data} />;
  }
  const running = status === "running";
  const holding = status === "awaiting_answers";
  /**
   * The panel obeys the same rule its button does, so there is one answer and not two.
   *
   * Enforcing it on the button alone would leave the panel open over a review that has since
   * stopped being askable — the reader is carried from a concluded pass to the running one it
   * started without this component unmounting. Deriving `open` instead of closing it in an
   * effect means the panel is never briefly open against a review that refuses it.
   */
  const showAsking = asking && ask(status) === null;
  if (!running && !report) {
    // The same dead end as a missing review and fixed the same way: a review that succeeded
    // without a report is unreadable, re-reading it will not produce one, and the reader
    // still needs somewhere to go.
    return (
      <ReviewUnavailable
        reviewId={reviewId}
        error={new Error("This review did not produce a report.")}
      />
    );
  }

  const summary = siblings.data?.find((item) => item.review_id === reviewId);
  const live = run.watching(reviewId) ? run.progress : undefined;
  const progress = watchedProgress(live, summary);
  const policyCount = (report?.policies_presented || []).length;
  const material = reviewed.filter((item) => item.material).length;
  const cleared = reviewed.length - material;
  const openQuestions = report?.overview.open_questions || [];
  const answered = pinnedCase.data?.answered?.answers || [];
  const askedEarlier = askingPass.data?.report?.overview?.open_questions || [];
  const title = report?.case_title || pinnedCase.data?.snapshot?.title || shortId(reviewId);

  // Both passes are stored, both judged the same atlas, and the only difference between them
  // is what the case says — so a verdict that moved is attributable to the answer and to
  // nothing else. Absent until the earlier pass has loaded, and absent entirely on a review
  // nobody was asked anything for.
  const judgedBefore = earlierPass.data?.report?.reviewed;

  // Only when there is a map to be shown in. Selecting first and switching second so the
  // node is already the selected one when the map arrives, rather than settling into place
  // and then changing under the reader.
  const hasAtlas = Boolean(repositoryRoot) && reviewed.length > 0;
  const showInAtlas = hasAtlas
    ? (nodeId: string) => {
        setAtlasNodeId(nodeId);
        openTab("atlas");
      }
    : null;
  /**
   * The same journey back: a node on the map to the finding written about it.
   *
   * Opening the row before switching tabs, for the same reason the citations do — the reasoning
   * is already unfolded when the reader arrives rather than unfolding under them. The panels
   * are force-mounted, so the row is in the document either way and one frame is only what the
   * tab switch needs before the scroll can land on it.
   */
  const openFinding = (nodeId: string) => {
    const reference = findingForNode(nodeId, reviewed);
    if (!reference) return;
    setOpenRow(reference);
    openTab("findings");
    requestAnimationFrame(() =>
      document
        .getElementById(reference)
        ?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  // How many verdicts this page can actually see. A tab watching the run's own record has
  // the counts and not the verdicts, and a band reporting 0 and 0 there would be answering a
  // question nobody can answer yet.
  const knownVerdicts = running
    ? (progress?.verdicts.filter((item) => item !== null).length ?? 0)
    : reviewed.length;

  const facts = verdictFacts({
    review: review.data,
    summary,
    indexedAtlas,
    repositoryRoot,
    reviewed,
    report,
    policyCount,
    progress,
    running,
    holding,
  });

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: "findings", label: "Findings", count: reviewed.length || undefined },
    ...(holding || answered.length > 0
      ? [
          {
            id: "questions" as TabId,
            label: holding ? "Open questions" : "Questions",
            count: holding ? openQuestions.length : answered.length,
          },
        ]
      : []),
    { id: "runlog", label: "Run log" },
    ...(hasAtlas ? [{ id: "atlas" as TabId, label: "Atlas" }] : []),
  ];
  // A tab that stops existing — the atlas, once its repository is gone — must not leave the
  // page showing nothing.
  const current = tabs.some((item) => item.id === tab) ? tab : "findings";

  /**
   * A section's contents, mounted on first visit and kept after.
   *
   * `forceMount` with the hidden state supplied here rather than the tab strip's own: Radix
   * takes an inactive panel out of the DOM, which would re-inspect every boundary each time
   * the reader came back to the map and lose wherever they had explored to. Gating on
   * `visited` is the other half — a reading that never opens the map makes no atlas query
   * at all.
   */
  const panel = (id: TabId) => {
    if (!visited.includes(id)) return null;
    return (
      <TabsContent key={id} value={id} forceMount hidden={current !== id}>
        {id === "findings" ? (
          <FindingsTab
            reviewId={reviewId}
            reviewed={reviewed}
            report={report}
            triage={triageByReference}
            policyCount={policyCount}
            branchId={branchId}
            openRow={openRow}
            onOpenRow={setOpenRow}
            onShowInAtlas={showInAtlas}
            progress={progress}
            running={running}
            holding={holding}
            judgedBefore={judgedBefore}
            askedEarlier={askedEarlier}
            answered={answered}
            undecided={undecided}
          />
        ) : null}
        {id === "questions" ? (
          <QuestionsTab
            reviewId={reviewId}
            investigation={review.data?.investigation}
            holding={holding}
            openQuestions={openQuestions}
            caseRevision={caseRevision}
            askedEarlier={askedEarlier}
            answered={answered}
            pending={answer.isPending || run.running}
            disabled={!repositoryRoot}
            error={answer.error}
            onSubmit={(answers) => answer.mutateAsync(answers)}
          />
        ) : null}
        {id === "runlog" && review.data ? (
          <RunLogTab
            review={review.data}
            progress={progress}
            reviewed={reviewed}
            watching={run.watching(reviewId)}
            holding={holding}
            running={running}
            openQuestionCount={openQuestions.length}
            answered={answered.length}
            caseRevision={caseRevision}
          />
        ) : null}
        {id === "atlas" && repositoryRoot ? (
          <AtlasTab
            repositoryRoot={repositoryRoot}
            reviewed={reviewed}
            selectedNodeId={atlasNodeId}
            onSelectNode={setAtlasNodeId}
            onOpenFinding={openFinding}
          />
        ) : null}
      </TabsContent>
    );
  };

  return (
    <div
      data-slot="review-page"
      // `page--asking` is a rule rather than a utility, and stays one: see its comment.
      className={cn(page, "pb-6", showAsking && "page--asking")}
    >
      <PageHeader
        title={title}
        parent={{ to: "/reviews", label: "Reviews" }}
        meta={<Badge variant="accent">case rev {caseRevision}</Badge>}
        action={
          <>
            {/* Before the primary control and quieter than it: taking the review away is
                something a reader does with a page they have finished with, and asking is
                what the page is for. */}
            <ExportAction
              reviewId={reviewId}
              available={Boolean(review.data?.markdown_report)}
            />
            <AskAction
              status={status}
              expanded={showAsking}
              onToggle={() => setAsking((value) => !value)}
            />
          </>
        }
      />

      {review.data ? (
        <RevisionStrip
          review={review.data}
          currentId={reviewId}
          reviews={allReviews.data || []}
          branches={branchLineages.data || []}
          onNewRevision={() => newRevision.mutate()}
          starting={newRevision.isPending || run.running || running}
          startError={newRevision.error instanceof Error ? newRevision.error : null}
        />
      ) : null}
      <PassesRail chain={chainAround(reviewId, siblings.data || [])} currentId={reviewId} />

      {holding ? (
        <HoldBanner
          questionCount={openQuestions.length}
          nextRevision={caseRevision === undefined ? null : caseRevision + 1}
          onAnswer={() => openTab("questions")}
        />
      ) : null}

      <VerdictBand
        material={
          running ? (progress?.verdicts.filter((item) => item === true).length ?? 0) : material
        }
        cleared={
          running ? (progress?.verdicts.filter((item) => item === false).length ?? 0) : cleared
        }
        judged={running ? (progress?.judged ?? 0) : reviewed.length}
        total={running ? (progress?.total ?? 0) : reviewed.length}
        mode={holding || knownVerdicts === 0 ? "counted" : running ? "live" : "settled"}
        countLabel={running ? `of ${progress?.total ?? 0} judged` : "boundaries judged"}
        facts={facts}
      />

      {/* Sections of one record, not destinations. Arrow keys move between them because a
          tablist that only answers to clicks is a row of buttons wearing the wrong role —
          which the primitive now handles, along with the roving tab stop through the strip. */}
      <Tabs value={current} onValueChange={(value) => openTab(value as TabId)}>
        <TabsList aria-label="Review sections">
          {tabs.map((item) => (
            <TabsTrigger key={item.id} value={item.id}>
              {item.label}
              {item.count === undefined ? null : <i>{item.count}</i>}
            </TabsTrigger>
          ))}
        </TabsList>

        {tabs.map((item) => panel(item.id))}
      </Tabs>

      <AskPanel reviewId={reviewId} open={showAsking} onClose={() => setAsking(false)} />
    </div>
  );
}
