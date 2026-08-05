/**
 * What the start step has chosen, and what pressing Run will therefore do.
 *
 * Extracted from the page so the button's decision is checkable without rendering
 * anything. Pure and synchronous: nothing here fetches or renders, and `runIntent`
 * states the decision once rather than leaving it to be re-derived at the call site.
 *
 * There is no case in here at all. A case stopped being an input on this step: every
 * run opens an empty one and the review's questions write it from the reader's answers.
 * Reviewing against an existing case happens where the case lives — on its review.
 */

export type StartSelection = {
  /** An indexed repository, chosen by hand or brought by an example. */
  repositoryRoot: string | null;
  /**
   * A repository path nothing has parsed yet. Offered, never silently selected: it is
   * where the folder picker opens.
   */
  path: string;
};

export const EMPTY_SELECTION: StartSelection = {
  repositoryRoot: null,
  path: "",
};

/**
 * A repository and a model are the two requirements (master plan §6C.1).
 *
 * The model is a requirement of the run rather than of the selection, which is why it is
 * an argument rather than a field: it is chosen in the top bar and outlives this page. It
 * is still checked here, because the button's `disabled` and what pressing it does have
 * to be derived from one function.
 */
export function isReady(selection: StartSelection, hasModel: boolean): boolean {
  return Boolean(selection.repositoryRoot) && hasModel;
}

/**
 * What pressing Run does. One kind: open an empty case about the repository and start
 * the review, whose questions are how the case gets written. `null` means the button is
 * disabled, and the button's own `disabled` is derived from the same selection — so a
 * run can never be started in a state this function calls impossible.
 */
export type RunIntent = { kind: "from-repository"; repositoryRoot: string } | null;

export function runIntent(selection: StartSelection, hasModel: boolean): RunIntent {
  const { repositoryRoot } = selection;
  if (!repositoryRoot || !hasModel) return null;
  return { kind: "from-repository", repositoryRoot };
}

/**
 * Whether one pasted line names a repository by address rather than by folder.
 *
 * The start step has a single field for "the project": a path walks the filesystem, an
 * address is checked out. The reader should never have to say which one they pasted —
 * this is the recognition, and it is deliberately narrow: URL schemes git itself clones
 * from, plus the scp-style `git@host:owner/repo` that hosting providers put on the
 * clipboard. A bare local path to a repository is not an address — it is a folder, and
 * indexing reviews it in place, which is the right treatment for it.
 */
export function looksLikeGitAddress(text: string): boolean {
  const line = text.trim();
  return /^(https?|ssh|git):\/\/\S+$/.test(line) || /^git@[^\s:]+:\S+$/.test(line);
}
