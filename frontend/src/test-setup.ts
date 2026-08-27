import "@testing-library/jest-dom/vitest";
import { act } from "react";

/**
 * jsdom has no `matchMedia`, and this frontend genuinely changes layout by width rather than
 * only styling it — the workbench is three panes, two panes, or one. So the stub is not a
 * silencer: it is how a test says which of those three it is looking at.
 */
let viewportWidth = 1440;
let reducedMotion = false;
let hasKeyboard = true;

type Registration = { query: string; listener: (event: MediaQueryListEvent) => void };

const listeners = new Set<Registration>();

function matches(query: string): boolean {
  if (query.includes("prefers-reduced-motion: reduce")) return reducedMotion;
  const min = /min-width:\s*(\d+)px/.exec(query);
  if (min) return viewportWidth >= Number(min[1]);
  const max = /max-width:\s*(\d+)px/.exec(query);
  if (max) return viewportWidth <= Number(max[1]);
  if (query.includes("prefers-color-scheme: dark")) return false;
  // The input, which is a separate question from the width: `setViewportWidth(390)` alone
  // still describes a very narrow desk, and a test that means "a phone" has to say so.
  if (query.includes("hover: hover")) return hasKeyboard;
  return false;
}

Object.defineProperty(globalThis, "matchMedia", {
  writable: true,
  value: (query: string) => {
    const list = {
      media: query,
      get matches() {
        return matches(query);
      },
      onchange: null,
      addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
        listeners.add({ query, listener });
      },
      removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
        for (const registration of listeners) {
          if (registration.listener === listener) listeners.delete(registration);
        }
      },
      dispatchEvent: () => false,
    };
    return list as unknown as MediaQueryList;
  },
});

/** Render at a desktop, tablet or phone width. Call before `render`. */
export function setViewportWidth(width: number) {
  viewportWidth = width;
  notify();
}

/** Render as a touch device — no hover, coarse pointer, no keyboard. Call before `render`. */
export function setHasKeyboard(value: boolean) {
  hasKeyboard = value;
  notify();
}

export function setReducedMotion(value: boolean) {
  reducedMotion = value;
  notify();
}

/**
 * A width change is a real user event — rotating a phone, dragging a window edge — and the
 * components listening to it set state. Notifying inside `act` is what makes that a settled
 * render by the time the calling test looks at the DOM, rather than a warning.
 */
function notify() {
  act(() => {
    for (const { query, listener } of listeners) {
      listener({ matches: matches(query), media: query } as MediaQueryListEvent);
    }
  });
}

/**
 * A working `localStorage`.
 *
 * Node now defines a `localStorage` global of its own, and without `--localstorage-file` it is
 * an empty object that shadows jsdom's real Storage — so `getItem` is not a function and the
 * theme preference cannot be read. This puts an in-memory Storage back.
 */
const store = new Map<string, string>();

// `globalThis`, matching the `matchMedia` definition above. Under jsdom the two are the same
// object, so this changes nothing for a component test; it is what keeps the file working
// under `@vitest-environment node`, where `window` is not defined at all.
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    get length() {
      return store.size;
    },
    key: (index: number) => [...store.keys()][index] ?? null,
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, String(value)),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
  } satisfies Storage,
});

export const VIEWPORT = { phone: 390, tablet: 1024, desktop: 1440 } as const;
