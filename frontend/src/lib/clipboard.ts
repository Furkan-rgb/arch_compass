import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Copying, which the product could not do at all.
 *
 * `navigator.clipboard` appeared nowhere in `src/`. The reviewer's next action after reading
 * a finding is to go to the file — they need the path, the qualified name, the commit, the
 * run id — and `Provenance` is nine rows of 64-character hashes whose only purpose is to be
 * pasted somewhere else.
 */

/** How long the control says it worked. Long enough to read, short enough not to be a state. */
const CONFIRM_MS = 1_500;

/**
 * Guarded, because the API is not always there and not always allowed.
 *
 * It is absent over plain HTTP on anything but localhost, absent in some embedded webviews,
 * and it *rejects* rather than returning false when the document does not have focus — which
 * happens for real, when the click that triggered it also moved focus to another window.
 * None of those is worth an unhandled rejection, and all of them mean the same thing to the
 * caller: the text is not on the clipboard, so do not claim it is.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Copy, and remember for a moment and a half that it worked.
 *
 * The confirmation lives here rather than in the button, because the two controls that copy
 * — the excerpt's own button and a path reference — should agree about how long "copied"
 * lasts, and a duration written twice is a duration that drifts.
 */
export function useCopy() {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = useCallback(async (text: string) => {
    const ok = await copyText(text);
    if (!ok) return false;
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), CONFIRM_MS);
    return true;
  }, []);

  return { copied, copy };
}
