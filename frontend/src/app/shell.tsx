import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { api } from "../api";
import { cn } from "../lib/cn";
import type { Tone } from "../lib/format";
import { useHasKeyboard } from "../lib/media";
import { runPollInterval } from "../lib/runs";
import { useTheme } from "../lib/theme";
import { StatusDot } from "../ui/badge";
import { Drawer } from "../ui/drawer";
import { Label } from "../ui/panel";
import { ShortcutSheet, useShortcutSheet } from "../ui/shortcuts";
import { Tooltip } from "../ui/tooltip";
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
  QuestionIcon,
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

/**
 * The same control, painted for the page rather than for the rail.
 *
 * Two of the rail's controls also belong in the navigation drawer, which is an ordinary
 * surface that inverts with the theme — so band ink, which is white in both themes, would be
 * white on white there. Only the three colours change; the shape, the target size and the
 * spacing are the rail's, because it is the same control and should read as one.
 */
const pageControl = "text-ink-2 hover:bg-sunken hover:text-ink focus-visible:outline-ink";

function ThemeToggle() {
  const { preference, cycle } = useTheme();
  const Glyph = preference === "light" ? SunIcon : preference === "dark" ? MoonIcon : MonitorIcon;
  const next = preference === "system" ? "light" : preference === "light" ? "dark" : "system";
  const says = `Theme: ${preference}. Switch to ${next}.`;
  return (
    // A tooltip rather than `title`: this is an icon with no label, so the sentence is the
    // only thing that says which of the three states the glyph is in — and `title` never
    // appears for a keyboard and never appears at all on a touch screen.
    <Tooltip content={says}>
      <button
        type="button"
        onClick={cycle}
        aria-label={says}
        className={cn(railControl, "min-w-9 justify-center px-0")}
      >
        <Glyph className="size-4" />
      </button>
    </Tooltip>
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
      // The chip prints a truncated model id and a dot, so the role and the state it is in
      // are visible nowhere else. That was a `title`, which a keyboard never sees.
      <Tooltip
        content={
          <>
            <span className="font-semibold text-ink">{role}</span>: {value || "not selected"}
            <span className="mt-0.5 block text-ink-3">{state.note}</span>
          </>
        }
        side="bottom"
      >
        <Link
          to="/settings"
          aria-label={`${role} model: ${value || "not selected"} — ${state.note}`}
          className={cn(
            railControl,
            "min-w-0 gap-1.5 font-mono text-[11px]",
            // Stacked means the drawer, which is a page surface rather than the rail.
            stacked && cn("justify-start", pageControl),
          )}
        >
          <StatusDot tone={state.tone} pulse={state.pulse} />
          <span className="sr-only">{role}</span>
          <span aria-hidden="true" className="max-w-[9rem] truncate">
            {value || "not selected"}
          </span>
        </Link>
      </Tooltip>
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

/**
 * A review that is running, said everywhere rather than only on the page watching it.
 *
 * The run page tells you that you can close it and come back to the address, and then every
 * trace of the run disappears the moment you do: no badge, no count, nothing on Policies or
 * Settings saying the workspace is busy. For a job measured in minutes, going and doing
 * something else is the ordinary case, so the one place that survives every route has to
 * carry it.
 *
 * The poll stops when the list empties — `refetchInterval` reads the last answer rather than
 * being a fixed timer — so a workspace with nothing running costs one request per mount and
 * no further traffic. The same query key the reviews page uses, so the two share one
 * request rather than each running their own.
 *
 * Nothing is rendered when the list is empty. An indicator that is always there, reading
 * "nothing running", is a count nobody can act on.
 */
function RunIndicator({ className }: { className?: string }) {
  const runs = useQuery({
    queryKey: ["review-runs"],
    queryFn: api.reviewRuns,
    refetchInterval: (query) => runPollInterval(query.state.data),
  });

  const running = runs.data ?? [];
  if (!running.length) return null;

  // One run goes to the run itself; more than one has no single address, so it goes to the
  // list that shows all of them.
  const to = running.length === 1 ? `/runs/${running[0].run_id}` : "/reviews";
  const label = running.length === 1 ? "1 review running" : `${running.length} reviews running`;

  return (
    <Link to={to} className={cn(railControl, "gap-2 whitespace-nowrap", className)}>
      {/* `neutral` and breathing, which is the reading the model chips already established:
          this is not a fourth state on the severity scale, it is the scale not knowing yet.
          `held` would be the wrong claim — nobody is waiting on the reader, the workspace is
          working. */}
      <StatusDot tone="neutral" pulse />
      {label}
    </Link>
  );
}

/** The nav as a column, for the phone drawer. Full labels here — there is room for them. */
function DrawerNav({ onNavigate }: { onNavigate: () => void }) {
  const group = (label: string, items: NavItem[]) => (
    <div>
      <Label className="px-2.5 pb-1.5">{label}</Label>
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
      <Label>Workspace</Label>
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

/**
 * The keyboard, discoverable with a pointer.
 *
 * `?` is how the sheet is opened by anyone who already knows it exists, which is nobody on
 * their first review — so the same thing is a quiet control in the rail, beside the theme
 * toggle, where the other settings-shaped controls are.
 */
function ShortcutsButton({ onOpen }: { onOpen: () => void }) {
  return (
    <Tooltip content="Keyboard shortcuts — press ?">
      <button
        type="button"
        onClick={onOpen}
        aria-label="Keyboard shortcuts"
        className={cn(railControl, "min-w-9 justify-center px-0")}
      >
        <QuestionIcon className="size-4" />
      </button>
    </Tooltip>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  const palette = useCommandPalette();
  const shortcuts = useShortcutSheet();
  const hasKeyboard = useHasKeyboard();
  const workspace = isWorkspaceRoute(location.pathname);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-svh flex-col bg-canvas text-ink">
      {/* `outline-band-ink`, because this lands on the rail rather than on the page.
          The ring is ink everywhere else, and ink on a light page is near-black — so the
          first thing a keyboard reaches on every screen drew a black ring on the black rail,
          around a black chip, and the one control whose entire job is to be findable by
          keyboard was invisible to it. The band's own ink is white in both themes, which is
          the only value that reads on this ground. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-sm focus:bg-ink focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-canvas focus-visible:outline-band-ink"
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

          <RunIndicator className="hidden md:inline-flex" />

          {/* The way to anything, and the reason the sidebar could go. Everything the nav
              lists is in here, plus every review and every repository by name.

              It gives its width back below `xl` and keeps only the icon and the word. The
              chips beside it are what a reader checks without meaning to — which repository
              root, which two models — and a 13rem box holding one word nobody has typed into
              yet is not worth the workspace's identity disappearing for 256 pixels. */}
          <button
            type="button"
            onClick={palette.open}
            aria-label="Search everything"
            className={cn(
              railControl,
              "gap-2 border border-band-rule text-band-ink-2 sm:justify-start xl:min-w-[13rem]",
            )}
          >
            <SearchIcon className="size-4 shrink-0" />
            <span className="hidden sm:inline">Search…</span>
            <kbd
              aria-hidden="true"
              className="ml-auto hidden rounded-xs border border-band-rule px-1 font-mono text-[10px] leading-4 xl:inline"
            >
              ⌘K
            </kbd>
          </button>

          {/* `lg`, which is where the hamburger goes. The two used to be `lg:hidden` and
              `xl:flex`, so between 1024 and 1280 — an ordinary window width — there was no
              drawer to open and no chips, and nothing on any page said which repository root
              the workspace pointed at or which two models it ran. */}
          <ModelChips className="hidden lg:flex" />
          {hasKeyboard ? <ShortcutsButton onOpen={shortcuts.open} /> : null}
          <ThemeToggle />
          <Link
            to="/start"
            className="ml-1 hidden min-h-9 shrink-0 items-center rounded-sm bg-band-ink px-3 text-[13px] font-semibold text-band transition hover:opacity-90 focus-visible:outline-band-ink sm:inline-flex"
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
          {/* The drawer is where the workspace says what it is, so the chips belong here
              too — which is what `stacked` was written for. It had no call site at all,
              so below the rail's own breakpoint nothing named the two models anywhere. */}
          <div className="min-w-0 rounded-md border border-rule bg-surface-2 p-1.5">
            <Label className="px-1 pb-1">Models</Label>
            <ModelChips stacked />
          </div>
          <RunIndicator className={cn(pageControl, "justify-start")} />
        </div>
      </Drawer>

      <CommandPalette
        open={palette.isOpen}
        onClose={palette.close}
        sections={NAV.map((item) => ({ to: item.to, label: item.label }))}
      />

      <ShortcutSheet open={shortcuts.isOpen} onClose={shortcuts.close} />
    </div>
  );
}
