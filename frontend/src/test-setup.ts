import "@testing-library/jest-dom/vitest";

if (!window.PointerEvent) {
  Object.defineProperty(window, "PointerEvent", {
    configurable: true,
    value: MouseEvent,
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
