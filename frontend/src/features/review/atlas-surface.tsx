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
export function reviewAnchors(review: Review): {
  nodeIds: string[];
  qualifiedNames: string[];
  /** How many distinct elements the cap left out — the thing the comment above promises to say. */
  dropped: number;
} {
  const seen = new Set<string>();
  const nodeIds: string[] = [];
  const qualifiedNames: string[] = [];
  let dropped = 0;
  // Every judged element before any of its context: the route takes forty anchors, and a
  // sweep large enough to reach that limit should still have all of its verdicts on the map.
  const inOrder = [
    ...review.findings.map((finding) => finding.candidate.participants.slice(0, 1)),
    ...review.findings.map((finding) => finding.candidate.participants.slice(1)),
  ].flat();
  for (const participant of inOrder) {
    const key = participant.node_id ?? `name:${participant.qualified_name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    // Counted rather than broken out of: the surface says how many it left behind, and it
    // cannot say so without walking to the end of the list.
    if (nodeIds.length + qualifiedNames.length >= MAX_SUBJECTS) {
      dropped += 1;
      continue;
    }
    if (participant.node_id) nodeIds.push(participant.node_id);
    else qualifiedNames.push(participant.qualified_name);
  }
  return { nodeIds: nodeIds.sort(), qualifiedNames: qualifiedNames.sort(), dropped };
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
      // The word, beside the hue and the mark. A card that carried only the other two said
      // exactly the same thing about a material finding and a cleared one.
      verdictLabel: finding ? verdictOf(finding.verdict).label : undefined,
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
 * What each request is, said in words rather than derived from the name of its enum.
 *
 * `No ${humanise(operation)} are recorded in this atlas` produced "No search are recorded in
 * this atlas" and "No forward neighbourhood are recorded in this atlas" — sentences built by a
 * template that was only ever right for the four operations whose names happen to be plural
 * nouns. Prose is not a transformation of an identifier, so it is written out.
 *
 * `asking` completes "Asking the atlas for …"; `empty` is the whole sentence for an answer of
 * nothing; `noun` is what the exploration is called once it is on the map.
 */
const OPERATIONS: Record<string, { asking: string; empty: string; noun: string }> = {
  children: {
    asking: "what this contains",
    empty: "The atlas records nothing inside this element.",
    noun: "Children",
  },
  dependencies: {
    asking: "what this depends on",
    empty: "This element depends on nothing the atlas recorded.",
    noun: "Dependencies",
  },
  dependants: {
    asking: "what depends on this",
    empty: "Nothing in this atlas depends on this element.",
    noun: "Dependants",
  },
  callers: {
    asking: "what calls this",
    empty: "Nothing in this atlas calls this element.",
    noun: "Callers",
  },
  implementations: {
    asking: "what implements this",
    empty: "Nothing in this atlas implements this element.",
    noun: "Implementations",
  },
  tests: {
    asking: "the tests that reach this",
    empty: "No test in this atlas reaches this element.",
    noun: "Tests",
  },
  forward_neighbourhood: {
    asking: "everything two hops out",
    empty: "Nothing is recorded within two hops of this element.",
    noun: "Two hops out",
  },
  reverse_neighbourhood: {
    asking: "everything two hops back",
    empty: "Nothing within two hops of this atlas reaches this element.",
    noun: "Two hops back",
  },
  search: {
    asking: "elements matching that term",
    empty: "Nothing in this atlas matches that term.",
    noun: "Search",
  },
  cycles: {
    asking: "the dependency cycles it recorded",
    empty: "This atlas records no dependency cycle.",
    noun: "Cycles",
  },
  signals: {
    asking: "the elements it raised signals against",
    empty: "This atlas raised no structural signal.",
    noun: "Signals",
  },
  shortest_path: {
    asking: "a path",
    empty: "No dependency path joins those two in this atlas.",
    noun: "Path",
  },
};

function operationOf(operation: string) {
  return (
    OPERATIONS[operation] ?? {
      asking: "that",
      empty: "The atlas has nothing to answer that with.",
      noun: humanise(operation),
    }
  );
}

/**
 * Counts, and the map's legend, as one line.
 *
 * "What does the red border mean" and "how many are red" are the same question asked twice,
 * and answering them in two places a hand's width apart is how a legend and a dashboard both
 * end up on a page that wanted neither.
 *
 * The counts are of what is **drawn**, not of what the review judged. They were of the review,
 * over a map that draws a bounded subset of it, so a sixty-finding review printed "Material 9"
 * above six red cards — a legend disagreeing with the picture it is a legend for. What is not
 * drawn is said in the header instead, where there is room to say why.
 */
function AtlasLegend({ counts, className }: { counts: Map<string, number>; className?: string }) {
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
  const { nodeIds, qualifiedNames, dropped } = anchors;
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
  /**
   * Taking one back off, and taking all of them off.
   *
   * The map only ever grew. Three presses of "Two hops out" turned a ninety-card
   * neighbourhood into a three-hundred-card mesh, held at `staleTime: Infinity` for the rest
   * of the session, and the only way back to the review's own shape was to reload the page.
   * The list of requests was already here and already the right thing to undo — nothing had
   * ever offered the reverse of `explore`.
   */
  const drop = (request: ExploreRequest) => {
    client.setQueryData<ExploreRequest[]>(exploredKey, (current = []) =>
      current.filter((item) => JSON.stringify(item) !== JSON.stringify(request)),
    );
  };
  const resetMap = () => {
    client.setQueryData<ExploreRequest[]>(exploredKey, []);
    // Both of these point at cards that may have just left the map, and a half-finished
    // gesture against an element that is gone is not a gesture anyone can finish.
    setSelectedNodeId(null);
    setPathStartNodeId(null);
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
   * The verdicts the map actually drew, which is what the legend beside it is a legend for.
   *
   * A finding is on the map when the element it was written about came back from the atlas.
   * Findings drop out for two reasons and the header says both: the map anchors on a bounded
   * number of elements, and an atlas rebuilt since the review can no longer hold one.
   */
  const drawnVerdicts = useMemo(() => {
    const placed = new Set(nodes.map((node) => node.candidateId).filter(Boolean));
    const counts = new Map<string, number>(VERDICT_ORDER.map((verdict) => [verdict, 0]));
    for (const finding of review.findings) {
      if (!placed.has(finding.candidate.id)) continue;
      counts.set(finding.verdict, (counts.get(finding.verdict) ?? 0) + 1);
    }
    return counts;
  }, [nodes, review]);
  const undrawn =
    review.findings.length - [...drawnVerdicts.values()].reduce((sum, count) => sum + count, 0);

  /**
   * What the reader has added, named the way the button that added it is named.
   *
   * Read off the stored requests rather than tracked beside them, for the same reason the
   * traced path is: a second copy of what is on the map is a second thing that can disagree
   * with it.
   */
  const added = useMemo(
    () =>
      explored.data.map((request) => {
        const noun = operationOf(request.operation).noun;
        const on = request.node_id
          ? nodes.find((node) => node.id === request.node_id)?.label
          : undefined;
        const label =
          request.operation === "search"
            ? `Search for ${(request.terms ?? []).join(" ")}`
            : on
              ? `${noun} of ${on}`
              : noun;
        return { id: JSON.stringify(request), label, onDrop: () => drop(request) };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [explored.data, nodes],
  );

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
      // A cycle is the same kind of answer as a path — a named set of relationships the
      // reader asked for by pressing something — and drawing it as an ordinary hairline in a
      // mesh of hairlines is why "Surface cycles" read as a button that did nothing. Whichever
      // of the two was asked for last is the one on the map.
      const { operation } = requests[index];
      if (operation === "shortest_path" || operation === "cycles") return explorations[index]?.data;
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
    const operation = operationOf(request.operation);
    if (query?.isLoading) return `Asking the atlas for ${operation.asking}…`;
    if (query?.error) return `The atlas did not answer the request for ${operation.asking}.`;
    if (!found.length) return operation.empty;
    const counted = !added.length
      ? found.length === 1
        ? "1 element, already on the map."
        : `${plural(found.length, "element")}, all already on the map.`
      : added.length === found.length
        ? `${plural(added.length, "element")}, added.`
        : `${plural(found.length, "element")}, ${added.length} of them new to the map.`;
    if (request.operation !== "cycles") return counted;
    // A cycle whose relationships are not pointed at is a handful of extra cards in a mesh.
    // The route returns the edges that make it one, and they are drawn the way a traced path
    // is — so the note says which line on the map is the answer.
    const round = query?.data?.relationships ?? [];
    return `${counted} The ${plural(round.length, "relationship")} that ${
      round.length === 1 ? "makes" : "make"
    } the cycles are drawn in full ink, as a traced path is.`;
  }, [lastExploration]);

  /**
   * Everything the reader has explicitly asked the atlas for, which no lens or filter may hide.
   *
   * The union over every exploration, not the last one. It was the last one — so exploring
   * implementations and then dependants dropped the implementations back out of the set, and
   * they lost the protection `visible-graph.ts` documents as absolute the moment the reader
   * asked a second question. Nothing takes an element back off this list except dropping the
   * exploration that put it there.
   */
  const revealedNodeIds = useMemo(() => {
    const revealed = new Set<string>();
    explored.data.forEach((request, index) => {
      if (request.operation === "shortest_path") return;
      for (const node of explorations[index]?.data?.node_summaries ?? []) {
        revealed.add(node.node_id);
      }
    });
    return [...revealed];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [explored.data, answered]);

  const traceNote = useMemo(() => {
    const requests = explored.data;
    for (let index = requests.length - 1; index >= 0; index -= 1) {
      if (requests[index].operation !== "shortest_path") continue;
      const query = explorations[index];
      if (query?.isLoading) return "Looking for a path…";
      if (query?.error) return "The atlas did not answer the request for a path.";
      const steps = query?.data?.node_ids?.length ?? 0;
      if (!steps) return operationOf("shortest_path").empty;
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
        explorations={added}
        onResetExplorations={resetMap}
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
              {/* What is bounded, said out loud, which is what `MAX_SUBJECTS` promised in a
                  comment and never did. Two sentences because they are two different reasons
                  a finding is not on the map, and a reader can act on the first. */}
              {dropped > 0 ? (
                <>
                  {" "}
                  This review names more elements than one read of the atlas anchors on, so{" "}
                  {plural(dropped, "element")} past the first {MAX_SUBJECTS} went unasked for.
                </>
              ) : null}
              {undrawn > 0 ? (
                <>
                  {" "}
                  The legend counts what is drawn: {plural(undrawn, "finding")} of{" "}
                  {review.findings.length} {undrawn === 1 ? "is" : "are"} not on the map, and
                  exploring from a card is the way to reach {undrawn === 1 ? "it" : "them"}.
                </>
              ) : null}
            </p>
            <AtlasLegend counts={drawnVerdicts} />
          </div>
        }
      />
    </div>
  );
}
