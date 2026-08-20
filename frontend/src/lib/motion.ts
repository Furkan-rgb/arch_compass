import { useEffect, useRef, useState } from "react";

/**
 * Reveal an element the first time it scrolls into view, once.
 *
 * The element carries `.reveal` and is finished by `data-revealed`, so the transition is
 * described in CSS and this hook only decides *when*. Anything the browser cannot observe —
 * jsdom under test, a reader who asked for reduced motion — is revealed immediately, which
 * is why no test has to wait for an animation.
 */
export function useReveal<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || revealed) return;
    const reduced = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || typeof IntersectionObserver === "undefined") {
      setRevealed(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setRevealed(true);
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [revealed]);

  return { ref, revealed };
}

/** Trap tab focus inside an open overlay, and restore it to the opener when it closes. */
export function useFocusTrap(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const container = ref.current;
    const opener = document.activeElement as HTMLElement | null;
    const focusable = () =>
      Array.from(
        container?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );

    focusable()[0]?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      opener?.focus?.();
    };
  }, [open, onClose]);

  return ref;
}

/**
 * Tell a scroller's edges apart from its ends.
 *
 * A capped list on macOS has no scrollbar until you touch it, so a row sliced by the bottom
 * edge reads as a rendering fault rather than as "there is more below". This marks which
 * edges still have content past them; the fade itself is described in CSS on `.scroll-edge`.
 *
 * It watches the box and its content, not just the scroll position, because the list also
 * changes length when the filter changes or the review is refetched.
 */
export function useScrollEdges<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);
  const [edges, setEdges] = useState({ top: false, bottom: false });

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const measure = () => {
      // A hair of tolerance: fractional scroll positions and zoom otherwise leave a fade
      // showing at a genuine end of the list.
      const slack = 1;
      setEdges((previous) => {
        const top = node.scrollTop > slack;
        const bottom = node.scrollTop + node.clientHeight < node.scrollHeight - slack;
        return previous.top === top && previous.bottom === bottom ? previous : { top, bottom };
      });
    };

    measure();
    node.addEventListener("scroll", measure, { passive: true });
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    for (const child of Array.from(node.children)) observer?.observe(child);

    return () => {
      node.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
    // Deliberately every render: the observed children are replaced wholesale when the
    // filter changes, and re-measuring an unchanged list costs one comparison.
  });

  return { ref, edges };
}
