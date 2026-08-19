import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { THEME_COLORS, applyTheme, resolveTheme } from "./theme";

// Read from the project root rather than from `import.meta.url`: under jsdom that is an
// http URL, and these two files are being checked as files on disk.
const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

describe("theme", () => {
  it("resolves an explicit preference without asking the machine", () => {
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("stamps the document so the CSS variables and the browser chrome agree", () => {
    expect(applyTheme("dark")).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(applyTheme("light")).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  /**
   * `index.html` paints the tab before this bundle exists, so it carries the two colours as
   * literals. They are `--canvas` from the stylesheet, copied by hand — this is the check
   * that notices when one of the three drifts.
   */
  it("keeps the pre-paint literals equal to the canvas token", () => {
    const light = /--canvas:\s*(#[0-9a-f]{6})/i.exec(css)?.[1];
    const dark = /\[data-theme="dark"\]\s*\{[^}]*--canvas:\s*(#[0-9a-f]{6})/i.exec(css)?.[1];

    expect(light).toBe(THEME_COLORS.light);
    expect(dark).toBe(THEME_COLORS.dark);
    expect(html).toContain(THEME_COLORS.light);
    expect(html).toContain(THEME_COLORS.dark);
  });
});
