/**
 * What the start step has chosen, and what pressing Run will therefore do.
 *
 * Extracted from the page because the answer to "which case will this run against" must be
 * checkable without rendering anything. It was component state and three handlers that each
 * set part of it, and the rules between them — a case fills the repository rail, the same
 * case pressed twice clears it, a run without a case starts from the repository instead —
 * lived only in the order those handlers happened to run in.
 *
 * Pure and synchronous: every function here takes the selection and returns the next one.
 * Nothing fetches, nothing renders, and `runIntent` states the decision the button makes
 * rather than leaving it to be re-derived at the call site.
 */

export type StartSelection = {
  /** An indexed repository, chosen or filled in from a case. */
  repositoryRoot: string | null;
  /** A chosen case, or `null` — which is a valid state, not an unfinished one. */
  caseId: string | null;
  /**
   * A repository named by a case that nothing has parsed yet. Offered, never silently
   * selected: it is where the folder picker opens.
   */
  path: string;
};

export type CaseChoice = {
  case_id: string;
  repository_root?: string | null;
};

export const EMPTY_SELECTION: StartSelection = {
  repositoryRoot: null,
  caseId: null,
  path: "",
};

/**
 * Choose a case, or clear it by choosing the one already chosen.
 *
 * The toggle exists because "no case" is a state worth getting back to. While a case was
 * required, clearing one only ever produced a run nobody could start; it is optional now
 * and the run genuinely differs without one — judged on the code alone, and asking for what
 * it could not weigh — so a reader who picked a case and changed their mind needs a way
 * back. The buttons already claim `aria-pressed`, which promises exactly this.
 *
 * Clearing a case leaves the repository alone. They are separate choices, and a reader
 * undoing one did not ask to undo the other.
 */
export function chooseCase(
  selection: StartSelection,
  item: CaseChoice,
  indexed: readonly string[],
): StartSelection {
  if (selection.caseId === item.case_id) {
    return { ...selection, caseId: null };
  }
  return applyRepositoryHint(
    { ...selection, caseId: item.case_id },
    item.repository_root,
    indexed,
  );
}

/**
 * A case that names an indexed repository fills the other rail too.
 *
 * The case already answers the question the repository rail asks, and making someone answer
 * it twice is asking them to repeat themselves. An unindexed path is offered rather than
 * selected: indexing is a real action with its own failure modes, and a rail that filled
 * itself with something that had never been parsed would be claiming a step had happened.
 *
 * The offer is always the latest one, and overwrites any earlier one: it decides where the
 * folder picker opens, so a repository named by a case nobody has chosen any more would open
 * it somewhere the page no longer points at.
 */
export function applyRepositoryHint(
  selection: StartSelection,
  root: string | null | undefined,
  indexed: readonly string[],
): StartSelection {
  if (!root) return selection;
  if (indexed.includes(root)) {
    return { ...selection, repositoryRoot: root };
  }
  return { ...selection, path: root };
}

/**
 * Choose a repository. Deliberately not a toggle, unlike a case.
 *
 * It is the one input a run cannot do without, so clearing it could only ever disable the
 * button — and switching to another repository is what someone actually wants, which is a
 * different click on a different card.
 */
export function chooseRepository(
  selection: StartSelection,
  root: string,
): StartSelection {
  return { ...selection, repositoryRoot: root };
}

/** A repository is the whole requirement; a case is optional (master plan §6C.1). */
export function isReady(selection: StartSelection): boolean {
  return Boolean(selection.repositoryRoot);
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

export function runIntent(selection: StartSelection): RunIntent {
  const { repositoryRoot, caseId } = selection;
  if (!repositoryRoot) return null;
  if (caseId) return { kind: "against-case", caseId, repositoryRoot };
  return { kind: "from-repository", repositoryRoot };
}
