import "@testing-library/jest-dom/vitest";

if (!window.PointerEvent) {
  Object.defineProperty(window, "PointerEvent", {
    configurable: true,
    value: MouseEvent,
  });
}
