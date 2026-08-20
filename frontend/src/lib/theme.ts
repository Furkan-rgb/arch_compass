import { useCallback, useEffect, useState } from "react";

/**
 * Light, dark, or whatever the machine is set to.
 *
 * `index.html` resolves the same preference in an inline script before first paint, so the
 * page never flashes the wrong theme. This module is the half that runs afterwards: it
 * changes the preference, writes it back, and keeps the browser chrome painted to match.
 * The two literals below are `--canvas` from `styles.css`, copied because a `meta` tag
 * cannot read a custom property — `theme.test.ts` reads both files and fails if they drift.
 */
export type ThemePreference = "light" | "dark" | "system";

export const STORAGE_KEY = "archcompass.theme";

export const THEME_COLORS = { light: "#f5f5f5", dark: "#0a0a0a" } as const;

/**
 * Storage access, guarded. A browser in private mode, or an embedded webview with storage
 * switched off, throws on access rather than returning null — and a theme preference is not
 * worth failing a page load over.
 */
function readStored(): string | null {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

function writeStored(preference: ThemePreference): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, preference);
  } catch {
    // A preference that cannot be remembered still applies for this visit.
  }
}

export function readPreference(): ThemePreference {
  const saved = readStored();
  return saved === "light" || saved === "dark" || saved === "system" ? saved : "system";
}

export function resolveTheme(preference: ThemePreference): "light" | "dark" {
  if (preference !== "system") return preference;
  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(preference: ThemePreference): "light" | "dark" {
  const theme = resolveTheme(preference);
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLORS[theme]);
  return theme;
}

export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);

  useEffect(() => {
    applyTheme(preference);
    writeStored(preference);
  }, [preference]);

  useEffect(() => {
    if (preference !== "system") return;
    const media = globalThis.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const listener = () => applyTheme("system");
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [preference]);

  const cycle = useCallback(() => {
    setPreference((current) =>
      current === "system" ? "light" : current === "light" ? "dark" : "system",
    );
  }, []);

  return { preference, setPreference, cycle, theme: resolveTheme(preference) };
}
