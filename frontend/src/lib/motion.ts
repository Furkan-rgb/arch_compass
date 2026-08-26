import { useEffect, useRef, useState } from "react";

/**
 * Whether this reader has asked for less movement, read once at the moment it is asked.
 *
 * Three hooks were each writing this line out, and `useSpecimen` and the atlas both want it
 * too. It is a function rather than a constant because the preference can be changed while
 * the page is open, and a module-level read would answer for whatever it was at import.
 *
 * `globalThis.matchMedia?.` because jsdom without the test setup's stub has none, and a
 * missing media query means "no preference recorded" rather than a page that fails to
 * render.
 */
export function prefersReducedMotion(): boolean {
  return Boolean(globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/**
 * Reveal an element the first time it scrolls into view, once.
 *
 * The element carries `.reveal` and is finished by `data-revealed`, so the transition is
 * described in CSS and this hook only decides *when*. Anything the browser cannot observe —
 * jsdom under test, a reader who asked for reduced motion — is revealed immediately, which
 * is why no test has to wait for an animation.
 *
 * The deadline is the important part, and it was missing. `.reveal` starts at `opacity: 0`,
 * so until this fires the content is not merely un-animated — it is not there. Anything that
 * renders the document without scrolling it got a page that was seventy per cent empty
 * ground: a print, a PDF export, a screenshot service, a link-preview crawler, a hash link
 * that jumps past a section, a browser that descheduled the observer. A bonus had become
 * load-bearing for the content existing at all. So a section that has not been observed
 * within 1.2 seconds reveals itself unconditionally, and `@media print` in `styles.css`
 * covers the case where no timer runs either.
 */
export function useReveal<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || revealed) return;
    if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") {
      setRevealed(true);
      return;
    }
    const deadline = window.setTimeout(() => setRevealed(true), 1200);
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          window.clearTimeout(deadline);
          setRevealed(true);
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 },
    );
    observer.observe(node);
    return () => {
      window.clearTimeout(deadline);
      observer.disconnect();
    };
  }, [revealed]);

  return { ref, revealed };
}

/**
 * Trap tab focus inside an open overlay, and restore it to the opener when it closes.
 *
 * `onClose` is held in a ref and deliberately not a dependency. It was one, and every call
 * site passes a fresh arrow on every render — so the effect tore down and re-ran on each of
 * them, and each run put focus back on the first focusable thing in the overlay. The review
 * page polls the run list every four seconds; that made typing into the drawer's search box
 * lose its keystrokes on a four-second cycle, which reads as a broken input rather than as a
 * focus bug.
 *
 * `[open]` is therefore the whole dependency list: the trap is set up when the overlay opens
 * and torn down when it closes, and nothing a parent re-renders can move focus.
 */
export function useFocusTrap(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement | null>(null);
  const close = useRef(onClose);

  // After every render rather than during one: a ref written in the render pass is a write
  // React is allowed to run twice or discard, and the handler below only reads it when a
  // key is actually pressed — which is always after the render that set it.
  useEffect(() => {
    close.current = onClose;
  });

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
        close.current();
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
  }, [open]);

  return ref;
}

/**
 * Everything an overlay owes the page behind it: a focus trap, and a page that stops
 * scrolling under it.
 *
 * The drawer carried both and the command palette carried neither, which is how a dialog
 * declaring `aria-modal="true"` came to let Tab walk into the page behind it. Two things
 * that are modal in the same sense should be modal in the same way, so this is the one
 * place either behaviour is written and both call sites take it whole.
 *
 * Returns the ref that goes on the dialog element — the trap needs to know which box it is
 * trapping inside.
 */
export function useOverlay(open: boolean, onClose: () => void) {
  const ref = useFocusTrap(open, onClose);

  useEffect(() => {
    if (!open) return;
    // The previous value rather than an empty string: overlays can be stacked — a drawer
    // with a sheet over it — and the inner one must give back what it found, not what the
    // document started with.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  return ref;
}

/**
 * Tell a scroller's edges apart from its ends.
 *
 * A capped list on macOS has no scrollbar until you touch it, so a row sliced by the bottom
 * edge reads as a rendering fault rather than as "there is more below". This marks which
 * edges still have content past them; the fade itself is described in CSS on `.scroll-edge`
 * and, for a strip that travels sideways, on `.scroll-edge-x`.
 *
 * All four edges, because the horizontal case is the worse one and had no answer at all. A
 * list that ends mid-row at least ends against a rule; a tab strip that ends mid-word reads
 * as a missing surface, and an excerpt sliced mid-token is indistinguishable from an excerpt
 * that is genuinely that short — which matters, because an excerpt is evidence. A caller
 * takes whichever pair its own axis scrolls on.
 *
 * It watches the box and its content, not just the scroll position, because the list also
 * changes length when the filter changes or the review is refetched.
 */
export function useScrollEdges<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);
  const [edges, setEdges] = useState({ top: false, bottom: false, left: false, right: false });

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const measure = () => {
      // A hair of tolerance: fractional scroll positions and zoom otherwise leave a fade
      // showing at a genuine end of the list.
      const slack = 1;
      setEdges((previous) => {
        const next = {
          top: node.scrollTop > slack,
          bottom: node.scrollTop + node.clientHeight < node.scrollHeight - slack,
          left: node.scrollLeft > slack,
          right: node.scrollLeft + node.clientWidth < node.scrollWidth - slack,
        };
        const unchanged = (Object.keys(next) as Array<keyof typeof next>).every(
          (edge) => previous[edge] === next[edge],
        );
        return unchanged ? previous : next;
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
