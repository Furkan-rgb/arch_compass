import { useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";
export type EffectiveTheme = Exclude<ThemePreference, "system">;

export const THEME_STORAGE_KEY = "archcompass.theme";

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function resolveTheme(
  preference: ThemePreference,
  systemPrefersDark: boolean,
): EffectiveTheme {
  return preference === "system"
    ? systemPrefersDark ? "dark" : "light"
    : preference;
}

/**
 * What the browser paints around the page, per theme.
 *
 * A hand-copy of `--canvas` from each material block in `styles.css` — the Porcelain one and
 * the Onyx one — because `<meta name="theme-color">` takes a literal colour and cannot read a
 * custom property. It is the one place in this app where a token value is written twice.
 *
 * It had already drifted: these were `#0d1211` and `#f2f5f4`, a pair of greens no token in
 * this design has ever held, left behind by a restyle that moved the canvas and had no reason
 * to look here. The token name is written beside each value so the next move of the canvas
 * has somewhere obvious to land, and `theme.test.tsx` reads both out of the stylesheet and
 * fails if they part company again.
 */
export const THEME_COLORS: Record<EffectiveTheme, string> = {
  light: "#f5f4f1", // --canvas, Porcelain
  dark: "#0b0d11", // --canvas, Onyx
};

function savedPreference(): ThemePreference {
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
  return isThemePreference(saved) ? saved : "system";
}

export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(savedPreference);
  const [systemPrefersDark, setSystemPrefersDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const effectiveTheme = resolveTheme(preference, systemPrefersDark);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const updateSystemTheme = (event: MediaQueryListEvent) =>
      setSystemPrefersDark(event.matches);
    setSystemPrefersDark(query.matches);
    query.addEventListener("change", updateSystemTheme);
    return () => query.removeEventListener("change", updateSystemTheme);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    document.documentElement.dataset.theme = effectiveTheme;
    document.documentElement.style.colorScheme = effectiveTheme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", THEME_COLORS[effectiveTheme]);
  }, [effectiveTheme, preference]);

  return { preference, effectiveTheme, setPreference };
}
