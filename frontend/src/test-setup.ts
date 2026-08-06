import "@testing-library/jest-dom/vitest";

if (!window.PointerEvent) {
  Object.defineProperty(window, "PointerEvent", {
    configurable: true,
    value: MouseEvent,
  });
}

/* Recent Node exposes its own `localStorage` global, and where it was started without a store
   file every method on it throws. It shadows jsdom's, so any component that remembers a
   preference — the ask panel's width — crashes the whole tree on mount. An in-memory store is
   what jsdom would have given, and a test that reads storage wants a store, not a file. */
if (typeof window.localStorage?.getItem !== "function") {
  const entries = new Map<string, string>();
  // On `Storage.prototype` and not on the object itself, because a test that makes storage
  // refuse a write does it by replacing `Storage.prototype.setItem` — an own method would
  // shadow that and the refusal would never be felt.
  Object.assign(Storage.prototype, {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => void entries.set(key, String(value)),
    removeItem: (key: string) => void entries.delete(key),
    clear: () => entries.clear(),
    key: (index: number) => [...entries.keys()][index] ?? null,
  });
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: Object.create(Storage.prototype) as Storage,
  });
}

/* jsdom lays nothing out, so it ships no `ResizeObserver` — and cmdk builds one as soon as a
   list is mounted. A stub that observes nothing is the honest shape: there are no sizes to
   report in a document with no layout. */
if (!window.ResizeObserver) {
  Object.defineProperty(window, "ResizeObserver", {
    configurable: true,
    value: class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  });
}
