import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { graceWindow } from "./grace-window";

/**
 * The grace window, driven one build at a time.
 *
 * It is the half of the answer that means the reader never sees a failure at all: the chunks
 * a tab is already holding stay on disk, so the navigation that used to 404 simply succeeds.
 * What happens once the window closes is a screen and not machinery —
 * `src/app/error-boundary.test.tsx` covers the fallback it lands on.
 *
 * The plugin's hooks are called directly rather than through a real `vite build`. A real
 * build would take ten seconds a case and would test rollup as much as this, and every claim
 * here is about which files are on disk after a hook ran — which is exactly what the hooks
 * decide on their own.
 */

let root: string;
let outDir: string;

/** One build, as the two hooks Vite calls around it, with `emit` standing in for rollup. */
function build(names: string[], emit: (assets: string) => void = () => {}) {
  const plugin = graceWindow(root);
  const hooks = plugin as unknown as {
    configResolved: (config: { root: string; build: { outDir: string } }) => void;
    buildStart: () => void;
    writeBundle: (options: unknown, bundle: Record<string, unknown>) => void;
  };
  hooks.configResolved({ root: "/", build: { outDir } });
  hooks.buildStart();

  const assets = join(outDir, "assets");
  mkdirSync(assets, { recursive: true });
  for (const name of names) writeFileSync(join(assets, name), `// ${name}`);
  writeFileSync(join(outDir, "index.html"), names.join("\n"));
  emit(assets);

  const bundle: Record<string, unknown> = { "index.html": {} };
  for (const name of names) bundle[`assets/${name}`] = {};
  hooks.writeBundle({}, bundle);
}

function assets(): string[] {
  return readdirSync(join(outDir, "assets")).sort();
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "grace-root-"));
  outDir = mkdtempSync(join(tmpdir(), "grace-out-"));
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
  rmSync(outDir, { recursive: true, force: true });
});

describe("the window itself", () => {
  it("keeps the previous build's chunks, which is what an open tab is asking for", () => {
    build(["route-AAA.js", "entry-AAA.js"]);
    build(["route-BBB.js", "entry-BBB.js"]);

    expect(assets()).toEqual(["entry-AAA.js", "entry-BBB.js", "route-AAA.js", "route-BBB.js"]);
  });

  it("is bounded: the build before last goes, so the directory does not grow for ever", () => {
    build(["route-AAA.js"]);
    build(["route-BBB.js"]);
    build(["route-CCC.js"]);

    expect(assets()).toEqual(["route-BBB.js", "route-CCC.js"]);
  });

  it("keeps nothing on the first build into an empty tree", () => {
    build(["route-AAA.js"]);
    expect(assets()).toEqual(["route-AAA.js"]);
  });
});

describe("what a build still gets fresh", () => {
  it("empties everything outside assets, so a removed public file does not linger", () => {
    build(["route-AAA.js"], () => writeFileSync(join(outDir, "old-favicon.svg"), "<svg/>"));
    expect(existsSync(join(outDir, "old-favicon.svg"))).toBe(true);

    build(["route-BBB.js"]);
    // The chunk survived because it is a generation; the root file did not, because the root
    // is what `emptyOutDir: true` used to clear and still has to be.
    expect(assets()).toContain("route-AAA.js");
    expect(existsSync(join(outDir, "old-favicon.svg"))).toBe(false);
  });
});

describe("a rebuild that changes nothing", () => {
  it("does not spend the window on a build that emitted the same files", () => {
    // The bug this pins was live for one commit and is the failure mode the whole plugin
    // exists to prevent, arriving by the back door. Recording a generation as "whatever is on
    // disk that was not already retained" makes an unchanged rebuild record *nothing*, and a
    // generation of nothing tells the next build to retain nothing — so the third build below
    // deleted every chunk a live tab was holding. Taking the generation from the bundle the
    // build actually emitted is what makes an unchanged rebuild a no-op rather than a reset.
    build(["route-AAA.js"]);
    build(["route-AAA.js"]);
    build(["route-BBB.js"]);

    expect(assets()).toEqual(["route-AAA.js", "route-BBB.js"]);
  });
});

describe("a ledger that cannot be read", () => {
  it("retains nothing rather than throwing, and says so", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      build(["route-AAA.js"]);
      writeFileSync(join(root, "node_modules/.tmp/grace-window.json"), "{ not json");

      expect(() => build(["route-BBB.js"])).not.toThrow();
      // Losing the ledger costs the whole window, which is the failure this plugin exists to
      // remove and not a fallback it degrades into: `route-AAA.js` is a file an open tab is
      // asking for by name, and it is gone. The `rm -rf node_modules` that usually causes it
      // leaves no other trace, so the line on the console is the only thing between a silent
      // window and one that was never open.
      expect(assets()).toEqual(["route-BBB.js"]);
      expect(warn).toHaveBeenCalledTimes(1);
      expect(warn.mock.calls[0]?.[0]).toContain("retains nothing and deletes 1 chunk(s)");
    } finally {
      warn.mockRestore();
    }
  });

  it("is quiet about a first build, which has no window to lose", () => {
    // Without this the assertion above would pass on a plugin that warned on every build,
    // and a warning that always fires is one nobody reads by the second week.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      build(["route-AAA.js"]);
      expect(warn).not.toHaveBeenCalled();
    } finally {
      warn.mockRestore();
    }
  });
});
