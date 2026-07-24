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
      ?.setAttribute("content", effectiveTheme === "dark" ? "#10141b" : "#f5f6f8");
  }, [effectiveTheme, preference]);

  return { preference, effectiveTheme, setPreference };
}
