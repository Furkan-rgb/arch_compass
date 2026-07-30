import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { ThemeControl } from "./components";
import {
  resolveTheme,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "./theme";

let systemPrefersDark = false;
const systemListeners = new Set<(event: MediaQueryListEvent) => void>();

function setSystemTheme(dark: boolean) {
  systemPrefersDark = dark;
  act(() => {
    systemListeners.forEach((listener) =>
      listener({ matches: dark } as MediaQueryListEvent),
    );
  });
}

beforeEach(() => {
  systemPrefersDark = false;
  systemListeners.clear();
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: systemPrefersDark,
      media: "(prefers-color-scheme: dark)",
      onchange: null,
      addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) =>
        systemListeners.add(listener),
      removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) =>
        systemListeners.delete(listener),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(cleanup);

describe("theme preference", () => {
  it.each([
    ["system", false, "light"],
    ["system", true, "dark"],
    ["light", true, "light"],
    ["dark", false, "dark"],
  ] satisfies Array<[ThemePreference, boolean, "light" | "dark"]>)(
    "resolves %s with system dark=%s to %s",
    (preference, systemDark, expected) => {
      expect(resolveTheme(preference, systemDark)).toBe(expected);
    },
  );

  // The control is a toggle group in single mode now, so it announces itself the way a
  // setting with three values should: a radio group, with exactly one item checked. The
  // assertions moved onto role="radio"/aria-checked for that reason and for no other — the
  // accessible names, and which one is on, are unchanged.
  it("defaults to system and follows operating-system changes", () => {
    render(<ThemeControl />);

    expect(screen.getByRole("radio", { name: "Use system theme" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "light");

    setSystemTheme(true);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("persists an explicit preference and ignores system changes", () => {
    render(<ThemeControl />);
    fireEvent.click(screen.getByRole("radio", { name: "Use light theme" }));

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");

    setSystemTheme(true);
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("restores a saved dark preference", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeControl />);

    expect(screen.getByRole("radio", { name: "Use dark theme" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });
});
