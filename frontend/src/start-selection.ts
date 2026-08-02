/**
 * What the start step has chosen, and what pressing Run will therefore do.
 *
 * Extracted from the page because the answer to "which case will this run against" must be
 * checkable without rendering anything. Pure and synchronous: nothing here fetches or
 * renders, and `runIntent` states the decision the button makes rather than leaving it to
 * be re-derived at the call site.
 *
 * There is no case-picking rule left in here. A case stopped being an input on this step:
 * the review writes one from the reader's answers, or an example brings its own — and an
 * example sets both fields at once, which needs no rule.
 */

export type StartSelection = {
  /** An indexed repository, chosen by hand or brought by an example. */
  repositoryRoot: string | null;
  /**
   * The case an example brought, or `null` — the ordinary state, in which the run opens
   * an empty case and the review's questions write it.
   */
  caseId: string | null;
  /**
   * A repository path nothing has parsed yet. Offered, never silently selected: it is
   * where the folder picker opens.
   */
  path: string;
};

export const EMPTY_SELECTION: StartSelection = {
  repositoryRoot: null,
  caseId: null,
  path: "",
};

/**
 * A repository and a model are the two requirements; a case is optional (master plan §6C.1).
 *
 * The model is a requirement of the run rather than of the selection, which is why it is an
 * argument rather than a field: it is chosen in the top bar and outlives this page. It is
 * still checked here, because the button's `disabled` and what pressing it does have to be
 * derived from one function.
 */
export function isReady(selection: StartSelection, hasModel: boolean): boolean {
  return Boolean(selection.repositoryRoot) && hasModel;
}

/**
 * What pressing Run does, stated once rather than re-derived at the button.
 *
 * `against-case` reviews the chosen case. `from-repository` opens an empty case about the
 * repository first, which is the path for someone who has not written one. `null` means the
 * button is disabled, and the button's own `disabled` is derived from the same selection —
 * so a run can never be started in a state this function calls impossible.
 */
export type RunIntent =
  | { kind: "against-case"; caseId: string; repositoryRoot: string }
  | { kind: "from-repository"; repositoryRoot: string }
  | null;

export function runIntent(selection: StartSelection, hasModel: boolean): RunIntent {
  const { repositoryRoot, caseId } = selection;
  if (!repositoryRoot || !hasModel) return null;
  if (caseId) return { kind: "against-case", caseId, repositoryRoot };
  return { kind: "from-repository", repositoryRoot };
}
