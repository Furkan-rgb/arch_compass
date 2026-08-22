import { useEffect, useState } from "react";

/**
 * Layout that genuinely differs by size, rather than the same layout made narrower.
 *
 * The workbench swaps between three panes, two panes with a context drawer, and a single
 * pane with a bottom sheet — which is a structural change, not a style, so it is decided in
 * JavaScript. Everything that is only a style stays in CSS.
 */
export function useMediaQuery(query: string, fallback = false): boolean {
  const [matches, setMatches] = useState(() => {
    const media = globalThis.matchMedia?.(query);
    return media ? media.matches : fallback;
  });

  useEffect(() => {
    const media = globalThis.matchMedia?.(query);
    if (!media) return;
    setMatches(media.matches);
    const listener = (event: MediaQueryListEvent) => setMatches(event.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [query]);

  return matches;
}

/**
 * One named breakpoint, because one is what genuinely changes a layout in JavaScript.
 *
 * There was a `useIsDesktop` at 1280px beside it with no call site at all. A width constant
 * nothing reads is worse than no constant: it looks like the place to add the next one, and
 * the two of them disagreed about which width "the desk" starts at while the stylesheet
 * quietly used a third. Everything that is only a style stays in CSS, where a breakpoint is
 * a class rather than a subscription and a re-render.
 */
export const useIsTabletUp = () => useMediaQuery("(min-width: 1024px)");
