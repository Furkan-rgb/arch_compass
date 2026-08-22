import { useSyncExternalStore } from "react";

/**
 * Opening the file a claim was measured from, in the reader's own editor.
 *
 * Every path in the product looks like a link and goes nowhere, and the thing a reviewer
 * does next is open the file. An editor scheme is the only way to do that from a browser,
 * and it is a per-machine fact rather than a workspace one: two people reading the same
 * review may be running different editors, and one of them may be reading it over SSH where
 * no local path resolves at all.
 *
 * So it is stored on the machine and it is **off by default**. A link that silently fails —
 * a `vscode://` URL on a machine with no VS Code — is worse than no link, because it costs a
 * click to discover and looks like the product being broken. Nothing is offered until
 * somebody says which editor they use.
 */
export const STORAGE_KEY = "archcompass.editor";

/** The three that take a path in a URL. `none` is the default and means no link is offered. */
export type EditorScheme = "none" | "vscode" | "cursor" | "file";

const SCHEMES: Record<Exclude<EditorScheme, "none">, { label: string; url: string }> = {
  vscode: { label: "VS Code", url: "vscode://file" },
  cursor: { label: "Cursor", url: "cursor://file" },
  // No line number: `file://` is the browser's own handler and has no way to carry one.
  file: { label: "The system handler", url: "file://" },
};

export const EDITOR_LABELS: Record<EditorScheme, string> = {
  none: "Do not offer a link",
  vscode: SCHEMES.vscode.label,
  cursor: SCHEMES.cursor.label,
  file: SCHEMES.file.label,
};

/**
 * Storage access, guarded, for the same reason `lib/theme.ts` guards it: a browser in
 * private mode throws on access rather than returning null, and an editor preference is not
 * worth failing a render over.
 */
export function readEditorScheme(): EditorScheme {
  try {
    const saved = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (saved === "vscode" || saved === "cursor" || saved === "file") return saved;
  } catch {
    // Not knowing which editor is the default answer anyway.
  }
  return "none";
}

/**
 * Everything currently rendering a path, so a chosen editor takes effect on the screen the
 * reader is looking at.
 *
 * `localStorage` fires no event in the tab that wrote it, and `PathRef` reads the scheme
 * during render — so choosing an editor in Settings did nothing visible until something else
 * happened to re-render the paths, which on an open review is a navigation away and back.
 * A preference that appears not to have applied is one somebody sets twice.
 *
 * The `storage` event covers the other direction: it fires only in *other* tabs, which is
 * exactly the case this set does not cover.
 */
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  globalThis.addEventListener?.("storage", listener);
  return () => {
    listeners.delete(listener);
    globalThis.removeEventListener?.("storage", listener);
  };
}

export function writeEditorScheme(scheme: EditorScheme): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, scheme);
  } catch {
    // A preference that cannot be remembered still applies for this visit.
  }
  for (const listener of listeners) listener();
}

/**
 * The scheme, as a value a component re-renders on.
 *
 * `useSyncExternalStore` rather than state plus an effect: the store is outside React and
 * the server snapshot is what an editor-less render should show anyway.
 */
export function useEditorScheme(): EditorScheme {
  return useSyncExternalStore(subscribe, readEditorScheme, () => "none" as EditorScheme);
}

/**
 * The URL for a path, or null where no editor has been chosen.
 *
 * The line goes on as `:12`, which is what both editor schemes take. A relative path is
 * refused rather than guessed at: an editor URL resolves against the filesystem root, so
 * half a path opens the wrong file or nothing, and neither is better than no link.
 */
export function editorHref(
  path: string,
  line?: number | null,
  scheme: EditorScheme = readEditorScheme(),
): string | null {
  if (scheme === "none" || !path.startsWith("/")) return null;
  const base = `${SCHEMES[scheme].url}${path}`;
  return scheme === "file" || !line ? base : `${base}:${line}`;
}
