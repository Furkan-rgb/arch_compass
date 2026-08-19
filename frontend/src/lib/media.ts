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

export const useIsDesktop = () => useMediaQuery("(min-width: 1280px)");
export const useIsTabletUp = () => useMediaQuery("(min-width: 1024px)");
