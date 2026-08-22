import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { api } from "../api";
import { cn } from "../lib/cn";
import type { Tone } from "../lib/format";
import { useTheme } from "../lib/theme";
import { StatusDot } from "../ui/badge";
import { Drawer } from "../ui/drawer";
import { CommandPalette, useCommandPalette } from "../ui/command-palette";
import {
  BookIcon,
  CaseIcon,
  CompassMark,
  FolderIcon,
  LayersIcon,
  MenuIcon,
  MonitorIcon,
  MoonIcon,
  PlayIcon,
  SearchIcon,
  SlidersIcon,
  SunIcon,
} from "../ui/icons";

/**
 * Everywhere you can go, in one row.
 *
 * The 232px sidebar is gone. It carried six links and a workspace path down the full height
 * of every screen, and the one surface that actually needs the width — the review desk, which
 * puts the queue, the model's argument and the code it rests on beside each other — was
 * paying for it on every one of them. Six labels fit in a rail; a rail costs 48px once.
 *
 * `short` is what the rail prints and `label` is the whole name. They differ only where the
 * whole name is a phrase — "Start a review" is what the drawer and the palette say, because
 * there is room to say it and because it is what somebody searching would type.
 */
type NavItem = { to: string; label: string; short: string; icon: typeof PlayIcon; end?: boolean };

const REVIEW_NAV: NavItem[] = [
  { to: "/start", label: "Start a review", short: "Start", icon: PlayIcon },
  { to: "/reviews", label: "Reviews", short: "Reviews", icon: LayersIcon },
];

const WORKSPACE_NAV: NavItem[] = [
  { to: "/repositories", label: "Repositories", short: "Repositories", icon: FolderIcon },
  { to: "/cases", label: "Architecture cases", short: "Cases", icon: CaseIcon },
  { to: "/policies", label: "Policies", short: "Policies", icon: BookIcon },
  { to: "/settings", label: "Models", short: "Models", icon: SlidersIcon },
];

const NAV = [...REVIEW_NAV, ...WORKSPACE_NAV];

/**
 * The routes that are a workspace rather than a document, and get the whole viewport.
 *
 * A review is not a page you scroll — it is a surface you work at, with a list down one side
 * that has to stay put while the column beside it changes. That needs a fixed height to
 * divide, which a `max-w-[1560px]` box inside a scrolling document cannot give it.
 *
 * Matched on the path rather than announced by the page, because a page that announces it in
 * an effect paints once with the padding first and the desk jumps on every navigation.
 */
const WORKSPACE_ROUTES = [/^\/reviews\/[^/]+$/];

const isWorkspaceRoute = (pathname: string) =>
  WORKSPACE_ROUTES.some((pattern) => pattern.test(pathname));

/**
 * A control in the rail.
 *
 * The rail is dark in both themes — it is the one chrome in the product that does not invert —
 * so its controls cannot borrow `ink`/`surface` from the page. They speak in the band tokens,
 * which is the same set the landing page's field band uses and the only place a fixed dark
 * ground is allowed to live.
 */
// `pointer-coarse` grows the target in both directions, not just the one. An icon-only
// control is square, so a floor on the height alone leaves a 36×44 button — tall enough to
// pass a test that measures one axis and still too narrow for a thumb.
const railControl =
  "inline-flex min-h-9 min-w-9 pointer-coarse:min-h-11 pointer-coarse:min-w-11 items-center justify-center gap-2 rounded-sm px-2.5 text-[13px] font-medium text-band-ink-2 transition hover:bg-white/8 hover:text-band-ink focus-visible:outline-band-ink";

function ThemeToggle() {
  const { preference, cycle } = useTheme();
  const Glyph = preference === "light" ? SunIcon : preference === "dark" ? MoonIcon : MonitorIcon;
  const next = preference === "system" ? "light" : preference === "light" ? "dark" : "system";
  return (
    <button
      type="button"
      onClick={cycle}
      title={`Theme: ${preference}. Switch to ${next}.`}
      aria-label={`Theme: ${preference}. Switch to ${next}.`}
      className={cn(railControl, "min-w-9 justify-center px-0")}
    >
      <Glyph className="size-4" />
    </button>
  );
}

/**
 * Which two models this workspace is running, as two links to the one page that changes them.
 *
 * A dot and a name rather than a labelled card: in a 48px rail there is one line to spend,
 * and what a reader checks here is whether something is selected at all. The role stays in
 * the accessible name so the link is still askable for by what it is.
 *
 * The dot reads the severity scale straight: a recorded failure is the red end, nothing
 * chosen is waiting on a person, and a selection that has not failed is settled and recedes.
 * Which is what the scale said before — it just resolved against the *page*, so on a light
 * theme `held` came out black on the black rail and the one state worth seeing was the one
 * that was invisible. `.on-band` on the header is what fixes that; see `styles.css`.
 *
 * What this cannot say is whether a provider is answering right now. `describe_workspace`
 * costs one row and no network on purpose, and the failure it does carry is the last one
 * recorded against the selection. Reachability is asked where somebody is waiting on the
 * answer, which is the chooser on `/settings`.
 */
function ModelChips({ className, stacked }: { className?: string; stacked?: boolean }) {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  const chip = (
    role: string,
    value: string | undefined,
    pinned: boolean | undefined,
    failure?: string,
  ) => {
    // Pending is not a fourth state on the scale — it is the scale not knowing yet. A dot
    // that breathes says "still asking" without claiming a grade the answer might contradict
    // a moment later.
    const state: { tone: Tone; pulse?: boolean; note: string } = workspace.isPending
      ? { tone: "neutral", pulse: true, note: "reading the workspace…" }
      : failure
        ? { tone: "material", note: failure }
        : value
          ? { tone: "cleared", note: pinned ? "selected · pinned" : "selected" }
          : { tone: "held", note: "not selected" };
    return (
      <Link
        to="/settings"
        aria-label={`${role} model: ${value || "not selected"} — ${state.note}`}
        title={`${role}: ${value || "not selected"}\n${state.note}`}
        className={cn(
          railControl,
          "min-w-0 gap-1.5 font-mono text-[11px]",
          stacked && "justify-start",
        )}
      >
        <StatusDot tone={state.tone} pulse={state.pulse} />
        <span className="sr-only">{role}</span>
        <span aria-hidden="true" className="max-w-[9rem] truncate">
          {value || "not selected"}
        </span>
      </Link>
    );
  };
  return (
    <div className={cn("flex min-w-0 items-center gap-0.5", stacked && "flex-col items-stretch", className)}>
      {chip(
        "Reasoning",
        workspace.data?.models.reasoning?.model,
        workspace.data?.models.pinned,
        // The recorded failure is against the reasoning selection alone — it is
        // `model_catalog_service.status().selection`, not a workspace-wide fault — so it may
        // not colour the embedding chip beside it.
        workspace.data?.models.failure || undefined,
      )}
      {chip("Embedding", workspace.data?.models.embedding?.model, workspace.data?.models.embedding_pinned)}
    </div>
  );
}

/** The nav as a column, for the phone drawer. Full labels here — there is room for them. */
function DrawerNav({ onNavigate }: { onNavigate: () => void }) {
  const group = (label: string, items: NavItem[]) => (
    <div>
      <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3">
        {label}
      </div>
      <ul className="grid gap-0.5">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex min-h-11 items-center gap-2.5 rounded-sm px-2.5 text-sm font-medium transition",
                  isActive ? "bg-sunken text-ink" : "text-ink-2 hover:bg-sunken hover:text-ink",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon className={cn("size-4", isActive ? "opacity-100" : "opacity-70")} />
                  {item.label}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <nav aria-label="Sections" className="grid gap-5">
      {group("Review", REVIEW_NAV)}
      {group("Workspace", WORKSPACE_NAV)}
    </nav>
  );
}

function WorkspacePath() {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  // `truncate` sets `white-space: nowrap`, which makes this element's min-content width the
  // whole path — so every box between it and the drawer's own width has to be allowed to be
  // narrower than its content. Truncation is a promise the ancestors have to keep.
  return (
    <div className="min-w-0 rounded-md border border-rule bg-surface-2 p-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3">Workspace</div>
      <div
        title={workspace.data?.workspace}
        className="mt-1.5 min-w-0 truncate font-mono text-[11px] text-ink-2"
      >
        {workspace.data?.workspace || "…"}
      </div>
      {workspace.data?.hosted ? (
        <div className="mt-2 text-[11px] leading-4 text-ink-3">
          Hosted demo — repositories are fetched from allowed hosts.
        </div>
      ) : null}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  const palette = useCommandPalette();
  const workspace = isWorkspaceRoute(location.pathname);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-svh flex-col bg-canvas text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-sm focus:bg-ink focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-canvas"
      >
        Skip to content
      </a>

      {/* One rail, dark in both themes, 48px, and the only chrome in the product.
          It is sticky rather than fixed so a document page scrolls under it and a workspace
          page can measure against it: the desk below is exactly `100svh - 3rem`. */}
      <header className="on-band sticky top-0 z-30 shrink-0 border-b border-band-rule bg-band text-band-ink">
        <div className="flex h-12 items-center gap-1 px-2 sm:px-3">
          <button
            type="button"
            className={cn(railControl, "min-w-9 justify-center px-0 lg:hidden")}
            aria-label="Open navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen(true)}
          >
            <MenuIcon className="size-5" />
          </button>

          <Link
            to="/"
            className={cn(railControl, "shrink-0 gap-2 px-2 text-band-ink hover:bg-transparent")}
          >
            <CompassMark className="size-[18px]" />
            <span className="text-[14px] font-bold tracking-tight">
              <span className="font-normal text-band-ink-2">Arch</span>Compass
            </span>
          </Link>

          <nav aria-label="Primary" className="ml-2 hidden items-center gap-0.5 lg:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(railControl, isActive && "bg-white/10 text-band-ink")
                }
              >
                {item.short}
              </NavLink>
            ))}
          </nav>

          <span className="flex-1" />

          {/* The way to anything, and the reason the sidebar could go. Everything the nav
              lists is in here, plus every review and every repository by name. */}
          <button
            type="button"
            onClick={palette.open}
            aria-label="Search everything"
            className={cn(
              railControl,
              "gap-2 border border-band-rule text-band-ink-2 sm:min-w-[13rem] sm:justify-start",
            )}
          >
            <SearchIcon className="size-4 shrink-0" />
            <span className="hidden sm:inline">Search…</span>
            <kbd
              aria-hidden="true"
              className="ml-auto hidden rounded-xs border border-band-rule px-1 font-mono text-[10px] leading-4 sm:inline"
            >
              ⌘K
            </kbd>
          </button>

          <ModelChips className="hidden xl:flex" />
          <ThemeToggle />
          <Link
            to="/start"
            className="ml-1 hidden min-h-9 shrink-0 items-center rounded-sm bg-band-ink px-3 text-[13px] font-semibold text-band transition hover:opacity-90 sm:inline-flex"
          >
            New review
          </Link>
        </div>
      </header>

      {/* A workspace route is handed the viewport and lays itself out inside it; a document
          route keeps the measured column it always had. */}
      <main
        id="main"
        tabIndex={-1}
        className={cn("min-w-0 outline-none", workspace && "flex min-h-0 flex-1 flex-col")}
      >
        {workspace ? (
          children
        ) : (
          <div className="mx-auto w-full max-w-[1560px] px-4 py-6 sm:px-6 sm:py-8">{children}</div>
        )}
      </main>

      <Drawer
        open={navOpen}
        onClose={() => setNavOpen(false)}
        side="left"
        title="ArchCompass"
        description="Review workbench"
      >
        <div className="grid min-w-0 gap-4 p-3">
          <DrawerNav onNavigate={() => setNavOpen(false)} />
          <WorkspacePath />
        </div>
      </Drawer>

      <CommandPalette
        open={palette.isOpen}
        onClose={palette.close}
        sections={NAV.map((item) => ({ to: item.to, label: item.label }))}
      />
    </div>
  );
}
