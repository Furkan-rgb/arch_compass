import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { ThemeControl } from "./components";
import {
  resolveTheme,
  THEME_COLORS,
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

function source(name: string): string {
  return readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");
}

/** `--canvas` as each material block actually declares it, read out of the stylesheet. */
function canvasTokens(): { light: string; dark: string } {
  const css = source("./styles.css");
  // `--atlas-canvas-bg` does not match: the colon is part of the name being looked for.
  const declared = [...css.matchAll(/--canvas:\s*(#[0-9a-f]{3,8})/g)].map(
    (match) => match[1],
  );
  // Porcelain is declared first and Onyx overrides it, which is the order the file is
  // written in and the order this depends on.
  expect(declared).toHaveLength(2);
  return { light: declared[0], dark: declared[1] };
}

beforeEach(() => {
  systemPrefersDark = false;
  systemListeners.clear();
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.head.innerHTML = '<meta name="theme-color" content="#000000" />';
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

/**
 * The browser chrome is the one place a token value is written outside the stylesheet, so it
 * is the one place that can drift without anything on screen looking wrong. It already had:
 * `#0d1211` and `#f2f5f4` survived a restyle that moved the canvas from a green pair to a
 * warm grey and an onyx, and nobody could have seen it — the tab bar is not part of the page.
 *
 * These tests read the real files rather than restating the values, which is what makes them
 * catch the next move of `--canvas` instead of having to be updated alongside it.
 */
describe("theme-color", () => {
  it("paints the browser chrome in the canvas token of each theme", () => {
    expect(THEME_COLORS).toEqual(canvasTokens());
  });

  it("writes the light canvas onto the meta tag and follows the theme", () => {
    const canvas = canvasTokens();
    render(<ThemeControl />);

    const meta = document.querySelector('meta[name="theme-color"]');
    expect(meta).toHaveAttribute("content", canvas.light);

    setSystemTheme(true);
    expect(meta).toHaveAttribute("content", canvas.dark);
  });

  it("keeps the pre-paint copy in index.html on the same two values", () => {
    // The inline script runs before the bundle and writes the tag itself, so it holds a
    // second copy of the pair. Both of its literals have to be canvas values, and the
    // static attribute it overwrites has to be one too.
    const html = source("../index.html");
    const canvas = canvasTokens();
    const literals = [...html.matchAll(/#[0-9a-f]{3,8}/g)].map((match) => match[0]);

    expect(literals.length).toBeGreaterThan(0);
    for (const literal of literals) {
      expect([canvas.light, canvas.dark]).toContain(literal);
    }
  });
});
