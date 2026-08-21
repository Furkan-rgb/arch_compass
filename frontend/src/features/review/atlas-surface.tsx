import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api, type AtlasQueryResult, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { VERDICT_ORDER, humanise, plural, splitQualified, verdictOf } from "../../lib/format";
import type { components } from "../../openapi.generated";
import { Button } from "../../ui/button";
import { Mark } from "../../ui/mark";
import { TONE_TEXT } from "../../ui/meta";
import { ErrorNotice } from "../../ui/states";
import { AtlasExplorer } from "../atlas/explorer";
import type { AtlasEdgeView, AtlasMetricView, AtlasNodeView } from "../atlas/graph";

type ExploreRequest = components["schemas"]["AtlasExploreRequest"];
type Signal = components["schemas"]["ObscuritySignal"];
type Participant = components["schemas"]["ParticipantResponse"];

/**
 * The review, as a map.
 *
 * Every other surface on this page is a list: the docket orders findings by what needs a
 * person, the delta orders them by what moved. Both answer "what next" and neither answers
 * "where". A candidate is a place in a structure, and two material findings in the same module
 * are a different problem from two in opposite corners of the repository — that is the one
 * question a list cannot be read for, and it is the only reason this surface exists.
 *
 * It is built from the review outward rather than from the repository inward. A map of the
 * whole atlas beside a review would be a second, unrelated thing on the page; what a reader
 * wants here is where these particular elements sit and what reaches them, so the
 * neighbourhood of every judged element is the map, and the rest is a click away.
 *
 * The verdict is on the card. An element that was examined and cleared is drawn as cleared,
 * not as an ordinary card: the difference between "found to be sound" and "never looked at" is
 * the whole value of an exhaustive sweep, and a map that erased it would undo what the review
 * is for.
 */

/**
 * How many elements the map opens on.
 *
 * The route takes forty ids at a time and answers with their whole neighbourhood, which is
 * already a few hundred cards for a real repository. Everything past this is reachable — the
 * detail panel's exploration is exactly the way to reach it — and what is dropped is said out
 * loud below, because a bounded view that does not say it is bounded reads as a complete one.
 */
const MAX_SUBJECTS = 40;

/**
 * Roughly how many cards the map should open with, and why it is a budget rather than a limit
 * per element.
 *
 * The route's neighbour bound is per anchor, so it multiplies: a review with eight findings
 * asks about sixteen elements, and twenty-five neighbours each is four hundred cards. A real
 * one came back with 235, which fit-to-view answered by zooming to fifteen percent — a grey
 * mesh that is technically the whole map and legibly nothing.
 *
 * So the budget is on the total and the per-anchor share is derived from it. Four is the floor
 * because an element drawn with fewer than that is a card with a stub rather than a
 * neighbourhood, and the reader can always ask for more: exploring from a card is what the
 * detail panel's whole middle section is for.
 */
const NODE_BUDGET = 90;
const MIN_NEIGHBOURS = 4;
const MAX_NEIGHBOURS = 25;

/** Every element of a result, keyed so repeated appearances collapse into one. */
function collectNodes(results: AtlasQueryResult[]) {
  return new Map(
    results.flatMap((result) => result.node_summaries ?? []).map((node) => [node.node_id, node]),
  );
}

/**
 * What was measured of each element, in the shape the detail panel reads.
 *
 * The review context returns these for every node it carries. The measurement keeps its
 * nature, scope and limitations, because a number whose scope the reader cannot see is a
 * number they will read as meaning more than it does.
 */
function collectMetrics(results: AtlasQueryResult[]) {
  const byNode = new Map<string, Map<string, AtlasMetricView>>();
  for (const value of results.flatMap((result) => result.metric_values ?? [])) {
    const metrics = byNode.get(value.node_id) || new Map<string, AtlasMetricView>();
    // Keyed by the metric, not appended: the same element arrives in the review context and
    // again in whatever the reader has explored since, carrying the same measurement each time.
    metrics.set(value.metric, {
      // The scope is a prefix on the wire — `local.physical_lines` — and it is already
      // reported as `scope`, so carrying it into the label spends a narrow column printing
      // "Local." six times over a set of numbers that share it.
      label: humanise(value.metric.split(".").at(-1) ?? value.metric),
      value: value.value,
      nature: value.nature,
      scope: value.scope,
      definition: value.definition,
      limitations: value.limitations,
    });
    byNode.set(value.node_id, metrics);
  }
  return byNode;
}

/** The structural signals raised against each element, deduplicated the same way. */
function collectSignals(results: AtlasQueryResult[]) {
  const byNode = new Map<string, Map<string, Signal>>();
  for (const signal of results.flatMap((result) => result.signals ?? [])) {
    const signals = byNode.get(signal.node_id) || new Map<string, Signal>();
    // One element can carry two signals of one code at two places, so where it was raised is
    // part of which signal it is.
    const where = signal.location ? `${signal.location.path}:${signal.location.start_line}` : "";
    signals.set(`${signal.code}\n${where}`, signal);
    byNode.set(signal.node_id, signals);
  }
  return byNode;
}

/**
 * The elements this review's map is drawn around, asked for the best way each one can be.
 *
 * Every participant of every candidate, not only the one the verdict lands on. A candidate is
 * n-ary by construction — a duplicated concept is a fact about a set of modules — and a map
 * that drew one participant of it would be drawing a fraction of the finding.
 *
 * A participant that recorded the atlas node it was detected on is asked for by that id, which
 * is exact. One that did not — every finding judged before the id travelled with it — is asked
 * for by qualified name, which is weaker: a name can answer to two nodes across a rebuild.
 * Weaker is the point. Without it the whole surface would be a sentence explaining that it
 * cannot draw an existing review, which is a worse answer than a map with a caveat.
 *
 * Sorted, so the same review asks the same question however its findings are ordered, and
 * deduplicated because one class can take part in two of the candidates examined.
 */
export function reviewAnchors(review: Review): { nodeIds: string[]; qualifiedNames: string[] } {
  const seen = new Set<string>();
  const nodeIds: string[] = [];
  const qualifiedNames: string[] = [];
  // Every judged element before any of its context: the route takes forty anchors, and a
  // sweep large enough to reach that limit should still have all of its verdicts on the map.
  const inOrder = [
    ...review.findings.map((finding) => finding.candidate.participants.slice(0, 1)),
    ...review.findings.map((finding) => finding.candidate.participants.slice(1)),
  ].flat();
  for (const participant of inOrder) {
    if (nodeIds.length + qualifiedNames.length >= MAX_SUBJECTS) break;
    const key = participant.node_id ?? `name:${participant.qualified_name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (participant.node_id) nodeIds.push(participant.node_id);
    else qualifiedNames.push(participant.qualified_name);
  }
  return { nodeIds: nodeIds.sort(), qualifiedNames: qualifiedNames.sort() };
}

export function reviewAtlasNodes(results: AtlasQueryResult[], review: Review): AtlasNodeView[] {
  // Matched by the atlas node the finding recorded, and by name only where it recorded none.
  //
  // Only where it recorded none. Registering both would let one finding light two cards: the
  // element it was actually detected on, and whatever else in the atlas now answers to that
  // qualified name. The id is the exact anchor, and where there is one it is the whole answer.
  const judged = new Map<string, Finding>();
  const involved = new Map<string, Finding>();
  const remember = (map: Map<string, Finding>, participant: Participant, finding: Finding) => {
    const key = participant.node_id ?? `name:${participant.qualified_name}`;
    if (!map.has(key)) map.set(key, finding);
  };
  for (const finding of review.findings) {
    const subject = finding.candidate.participants[0];
    if (subject) remember(judged, subject, finding);
    // Every other participant, so the map can say why a card it drew is there without
    // claiming a verdict was written about it.
    for (const participant of finding.candidate.participants.slice(1)) {
      remember(involved, participant, finding);
    }
  }
  const metrics = collectMetrics(results);
  const signals = collectSignals(results);

  return [...collectNodes(results).values()].map((node): AtlasNodeView => {
    const name = `name:${node.qualified_name}`;
    const finding = judged.get(node.node_id) ?? judged.get(name);
    const context = involved.get(node.node_id) ?? involved.get(name);
    const raised = [...(signals.get(node.node_id)?.values() || [])];
    return {
      id: node.node_id,
      label: splitQualified(node.qualified_name).leaf || node.qualified_name,
      qualified: node.qualified_name,
      path: node.location
        ? `${node.path}:${node.location.start_line}-${node.location.end_line}`
        : node.path,
      kind: node.node_type,
      isPublic: node.is_public,
      tone: finding ? verdictOf(finding.verdict).tone : undefined,
      candidateId: finding?.candidate.id,
      description: finding
        ? `${verdictOf(finding.verdict).label}. ${finding.reasoning}`
        : context
          ? `Part of the shape behind "${context.candidate.summary}".`
          : undefined,
      metrics: [...(metrics.get(node.node_id)?.values() || [])],
      signals: raised,
      signalCount: raised.length,
    };
  });
}

export function reviewAtlasEdges(
  results: AtlasQueryResult[],
  nodes: AtlasNodeView[],
): AtlasEdgeView[] {
  const known = new Set(nodes.map((node) => node.id));
  const seen = new Set<string>();
  const edges: AtlasEdgeView[] = [];
  for (const edge of results.flatMap((result) => result.relationships ?? [])) {
    if (!known.has(edge.source_id) || !known.has(edge.target_id)) continue;
    if (seen.has(edge.edge_id)) continue;
    seen.add(edge.edge_id);
    edges.push({
      id: edge.edge_id,
      sourceId: edge.source_id,
      targetId: edge.target_id,
      kind: edge.edge_type,
      confidence: edge.confidence,
    });
  }
  return edges;
}

/**
 * Counts, and the map's legend, as one line.
 *
 * "What does the red border mean" and "how many are red" are the same question asked twice,
 * and answering them in two places a hand's width apart is how a legend and a dashboard both
 * end up on a page that wanted neither.
 */
function AtlasLegend({ review, className }: { review: Review; className?: string }) {
  const counts = new Map<string, number>(VERDICT_ORDER.map((verdict) => [verdict, 0]));
  for (const finding of review.findings) {
    counts.set(finding.verdict, (counts.get(finding.verdict) ?? 0) + 1);
  }

  return (
    <dl className={cn("flex flex-wrap items-center gap-x-5 gap-y-2", className)}>
      {VERDICT_ORDER.map((verdict) => {
        const descriptor = verdictOf(verdict);
        return (
          <div key={verdict} className="inline-flex items-center gap-1.5">
            <Mark
              shape={descriptor.glyph}
              className={cn("size-[13px]", TONE_TEXT[descriptor.tone])}
            />
            <dt className="font-mono text-[10px] uppercase tracking-[0.13em] text-ink-3">
              {descriptor.label}
            </dt>
            <dd className="font-mono text-[12px] font-semibold tabular-nums text-ink">
              {counts.get(verdict) ?? 0}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export function AtlasSurface({
  review,
  onOpen,
}: {
  review: Review;
  onOpen?: (candidateId: string) => void;
}) {
  const client = useQueryClient();
  const root = review.repository.path;
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  /* Which element a traced path runs from. Local, because it is a half-finished gesture rather
     than a fact about the review: the reader picks a start, then picks an end. */
  const [pathStartNodeId, setPathStartNodeId] = useState<string | null>(null);

  const anchors = useMemo(() => reviewAnchors(review), [review]);
  const { nodeIds, qualifiedNames } = anchors;
  const byName = qualifiedNames.length && !nodeIds.length;
  const neighbours = Math.min(
    MAX_NEIGHBOURS,
    Math.max(MIN_NEIGHBOURS, Math.round(NODE_BUDGET / (nodeIds.length + qualifiedNames.length))),
  );

  // One request for the whole neighbourhood, which is what makes the map about this review.
  // The neighbourhoods of a review's candidates overlap almost entirely, so one inspection per
  // finding would fetch the same packages and the same edges once per finding, with one
  // loading state each. Missing ids are skipped by the route, so a since-reindexed repository
  // draws what survived rather than failing.
  const context = useQuery({
    queryKey: ["review-context", root, nodeIds, qualifiedNames, neighbours],
    queryFn: () => api.reviewContext(root, nodeIds, qualifiedNames, neighbours),
    enabled: nodeIds.length + qualifiedNames.length > 0,
  });

  /**
   * What the reader has explored from this map, kept as the requests that produced it.
   *
   * In the query cache rather than in component state, because state does not survive leaving
   * the page: the review itself stays cached across a navigation, and every path traced, cycle
   * surfaced and term searched would be thrown away — losing the reading and keeping the bill.
   * Requests and not results: a request is small, comparable and replayable, and holding the
   * results is what the cache is for.
   */
  const exploredKey = useMemo(() => ["atlas-explored", root, anchors], [root, anchors]);
  const explored = useQuery({
    queryKey: exploredKey,
    // Never fetched. This query is somewhere to keep a list, and its answer before anyone has
    // explored anything is that nothing has been.
    queryFn: () => [] as ExploreRequest[],
    initialData: [] as ExploreRequest[],
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const explore = (request: ExploreRequest) => {
    client.setQueryData<ExploreRequest[]>(exploredKey, (current = []) => [
      // The same question asked twice replaces its earlier answer instead of standing beside
      // it: two identical explorations are one exploration.
      ...current.filter((item) => JSON.stringify(item) !== JSON.stringify(request)),
      request,
    ]);
  };
  const explorations = useQueries({
    queries: explored.data.map((request) => ({
      queryKey: ["repository-explore", request],
      queryFn: () => api.exploreRepository(request.root_path, request),
      // The atlas this review pinned is immutable, so an exploration of it is answered once
      // and then kept — for as long as the list that names it is kept.
      staleTime: Infinity,
      gcTime: Infinity,
    })),
  });

  /* `useQueries` returns a new array on every render, so the map is memoised against which of
     the explorations have answered rather than against the array holding them — laying the
     graph out is the expensive part of this surface, and doing it again on every keystroke in
     the map's own search box would show. */
  const answered = explorations.map((query) => (query.data ? "1" : "0")).join("");
  const results = useMemo(
    () => [
      ...(context.data ? [context.data] : []),
      ...explorations.flatMap((query) => (query.data ? [query.data] : [])),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [context.data, explored.data, answered],
  );
  const nodes = useMemo(() => reviewAtlasNodes(results, review), [results, review]);
  const edges = useMemo(() => reviewAtlasEdges(results, nodes), [results, nodes]);

  /**
   * The path the reader last asked for, as the two sets the map draws it with.
   *
   * What is drawn is read off the answer rather than tracked beside it: the route returns the
   * elements and the relationships of the path it found, and a page keeping its own copy of
   * that would be able to disagree with the thing it is drawing. Which answer is the path is
   * found by the request instead — those are ours, so matching on one cannot drift the way
   * matching on the server's echo of it could.
   */
  const traced = useMemo(() => {
    const requests = explored.data;
    for (let index = requests.length - 1; index >= 0; index -= 1) {
      if (requests[index].operation === "shortest_path") return explorations[index]?.data;
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [explored.data, answered]);
  const highlightedNodeIds = useMemo(() => traced?.node_ids ?? [], [traced]);
  const highlightedEdgeIds = useMemo(
    () => (traced?.relationships ?? []).map((edge) => edge.edge_id),
    [traced],
  );

  /**
   * What the reader's last request came back with, said out loud and counted exactly.
   *
   * An atlas answers plenty of honest questions with nothing — an element nothing depends on,
   * two elements with no path between them — and the map's response to nothing is to stay
   * exactly as it was. Without a sentence, pressing "Dependants" on a leaf is
   * indistinguishable from pressing a broken button.
   *
   * "Found" and "added" are counted apart because they are different answers. An exploration
   * that returns one element already on the map has told the reader something true, and
   * saying "1 element added" over a map whose count did not move is worse than saying nothing.
   */
  const lastExploration = useMemo(() => {
    const requests = explored.data;
    for (let index = requests.length - 1; index >= 0; index -= 1) {
      if (requests[index].operation === "shortest_path") continue;
      const before = new Set(
        [
          ...(context.data?.node_summaries ?? []),
          ...explorations
            .slice(0, index)
            .flatMap((query) => query.data?.node_summaries ?? []),
        ].map((node) => node.node_id),
      );
      const found = explorations[index]?.data?.node_summaries ?? [];
      return {
        request: requests[index],
        query: explorations[index],
        found: found.map((node) => node.node_id),
        added: found.map((node) => node.node_id).filter((id) => !before.has(id)),
      };
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.data, explored.data, answered]);

  const exploreNote = useMemo(() => {
    if (!lastExploration) return undefined;
    const { request, query, found, added } = lastExploration;
    const named = humanise(request.operation).toLocaleLowerCase();
    if (query?.isLoading) return `Asking the atlas for ${named}…`;
    if (query?.error) return `The atlas did not answer the request for ${named}.`;
    if (!found.length) return `No ${named} are recorded in this atlas.`;
    if (!added.length) {
      return found.length === 1
        ? "1 element, already on the map."
        : `${plural(found.length, "element")}, all already on the map.`;
    }
    if (added.length === found.length) return `${plural(added.length, "element")}, added.`;
    return `${plural(found.length, "element")}, ${added.length} of them new to the map.`;
  }, [lastExploration]);

  /** Whatever the last exploration brought back, which no lens may then hide. */
  const revealedNodeIds = useMemo(() => lastExploration?.found ?? [], [lastExploration]);

  const traceNote = useMemo(() => {
    const requests = explored.data;
    for (let index = requests.length - 1; index >= 0; index -= 1) {
      if (requests[index].operation !== "shortest_path") continue;
      const query = explorations[index];
      if (query?.isLoading) return "Looking for a path…";
      if (query?.error) return "The atlas did not answer the request for a path.";
      const steps = query?.data?.node_ids?.length ?? 0;
      if (!steps) return "No dependency path joins those two in this atlas.";
      return `A path of ${plural(steps, "element")}, drawn on the map.`;
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [explored.data, answered]);

  // The neighbourhood read and the explorations the reader asked for are separate requests
  // against the same atlas, so the one that failed is the one re-run — re-running the whole set
  // would redraw a map the reader is already looking at to fix one missing path.
  const failedQuery = context.error ? context : explorations.find((query) => query.error);
  const loading = context.isLoading || explorations.some((query) => query.isLoading);

  if (!review.findings.length) {
    return (
      <p className="text-sm leading-6 text-ink-2">
        This review composed no findings, so there is nothing to place. The atlas it read is
        still recorded against it — {plural(review.atlas.node_count, "element")} and{" "}
        {plural(review.atlas.edge_count, "edge")} — but a map of a review can only draw what the
        review looked at.
      </p>
    );
  }

  if (!nodeIds.length && !qualifiedNames.length) {
    return (
      <p className="text-sm leading-6 text-ink-2">
        None of this review's findings named an element, so there is nothing to place them on.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* The notice says what failed; the button beside it is the only thing that can act on
          that, and it re-runs the one request rather than the whole set — re-running them all
          would redraw a map the reader is already looking at to fix one missing path. */}
      {failedQuery?.error ? (
        <div className="space-y-2">
          <ErrorNotice error={failedQuery.error} title="The atlas did not answer" />
          <Button
            variant="secondary"
            size="sm"
            disabled={failedQuery.isFetching}
            onClick={() => void failedQuery.refetch()}
          >
            {failedQuery.isFetching ? "Trying again…" : "Try again"}
          </Button>
        </div>
      ) : null}

      <AtlasExplorer
        nodes={nodes}
        edges={edges}
        loading={loading}
        emptyMessage="This review's elements are no longer in the indexed atlas."
        // The lens that answers the question this surface exists for: where the findings are,
        // and what reaches them. Structure draws containment only, which on a review's
        // neighbourhood is a scatter of unconnected cards; dependencies draws every edge in
        // the neighbourhood, which on a real repository is a mesh nobody can read. Both are
        // one press away.
        initialLens="judged"
        selectedNodeId={selectedNodeId}
        onSelectNode={setSelectedNodeId}
        onOpenFinding={onOpen}
        onExploreNode={(nodeId, operation, depth) =>
          explore({
            root_path: root,
            operation,
            node_id: nodeId,
            depth: depth ?? 1,
            limit: 60,
          })
        }
        onExploreAtlas={(operation) => explore({ root_path: root, operation, limit: 60 })}
        onSearch={(term) =>
          explore({
            root_path: root,
            operation: "search",
            terms: term.trim().split(/\s+/).slice(0, 10),
            limit: 30,
          })
        }
        pathStartNodeId={pathStartNodeId}
        onSetPathStart={setPathStartNodeId}
        onTracePath={(targetNodeId) => {
          if (!pathStartNodeId) return;
          explore({
            root_path: root,
            operation: "shortest_path",
            node_id: pathStartNodeId,
            target_id: targetNodeId,
            limit: 60,
          });
        }}
        highlightedNodeIds={highlightedNodeIds}
        highlightedEdgeIds={highlightedEdgeIds}
        exploreNote={exploreNote}
        traceNote={traceNote}
        revealedNodeIds={revealedNodeIds}
        header={
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 border-b border-rule px-3 py-3">
            <p className="max-w-[54ch] text-sm leading-6 text-ink-2">
              What this review examined, in the structure it found it in. Every card and every
              connector is read from the atlas the review was judged against — never from the
              repository as it stands now.
              {/* Where the anchors were resolved by name the map is a degree less certain
                  than it looks, and saying so is cheaper than a reader discovering it. */}
              {byName ? (
                <>
                  {" "}
                  This review recorded names rather than atlas elements, so its cards were
                  matched by name — a renamed element is missing rather than moved.
                </>
              ) : null}
            </p>
            <AtlasLegend review={review} />
          </div>
        }
      />
    </div>
  );
}
