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
import { BrandMark } from "../ui/brand";
import { Drawer } from "../ui/drawer";
import { Label } from "../ui/panel";
import { KeyCap, ShortcutSheet, useShortcutSheet } from "../ui/shortcuts";
import { Tooltip } from "../ui/tooltip";
import { CommandPalette, useCommandPalette } from "../ui/command-palette";
import {
  BookIcon,
  CaseIcon,
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
 * What to call the screen at a path, for the one caller that needs a name rather than a link.
 *
 * The tab title was a single sentence baked into `index.html`, so eight routes announced
 * themselves identically to a screen reader, to the history and to a row of open tabs. The
 * names already existed — they are the labels the rail and the palette print — so this is the
 * lookup rather than a second table that can disagree with the first.
 *
 * A nested path takes its parent's name: `/reviews/:id` is a review, and "Reviews" is a truer
 * answer than the product's own name. A route that knows more than its section does says so
 * itself and wins, because it sets the title from deeper in the tree — see `run-page.tsx`.
 */
export function pageName(pathname: string): string | undefined {
  return NAV.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`))?.label;
}

/**
 * The routes that are a workspace rather than a document, and are handed the bare viewport.
 *
 * Not because the review is wider — it draws itself in the same `76rem` measure every
 * document route gets. It is that its surface tabs are a full-bleed strip pinned under the
 * rail, and a strip that stops at the edge of a padded, centred box is a rule that floats in
 * the middle of the page rather than one that divides it. The page needs the container's own
 * edges and its own height to hang that from.
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
//
// `relative` so the nav link can hang its "you are here" underline off the control's own box.
const railControl =
  "relative inline-flex min-h-9 min-w-9 pointer-coarse:min-h-11 pointer-coarse:min-w-11 items-center justify-center gap-2 rounded-sm px-2.5 text-[13px] font-medium text-band-ink-2 transition hover:bg-white/8 hover:text-band-ink focus-visible:outline-band-ink";

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
    // a moment later. A query that *failed* is not a state on the scale either: `held` would
    // grade the workspace as waiting on a person, which is a claim about a configuration the
    // chip could not read.
    const state: { tone: Tone; pulse?: boolean; note: string } = workspace.isPending
      ? { tone: "neutral", pulse: true, note: "reading the workspace…" }
      : workspace.isError
        ? { tone: "neutral", note: "the workspace did not answer" }
        : failure
          ? { tone: "material", note: failure }
          : value
            ? { tone: "cleared", note: pinned ? "selected · pinned" : "selected" }
            : { tone: "held", note: "not selected" };
    // The visible string follows the state rather than the value, because an absence of data
    // is not a fact about the workspace. It used to print "not selected" from the first frame
    // and for ever after a failed fetch, which asserts a definite negative about the team's
    // own configuration on every screen — and said it beside a tooltip reading "reading the
    // workspace…". The charter's rule is that an explicit unknown outranks an implied one.
    const shown = workspace.isPending
      ? "reading…"
      : workspace.isError
        ? "could not read"
        : value || "not selected";
    return (
      // The chip prints a truncated model id and a dot, so the role and the state it is in
      // are visible nowhere else. That was a `title`, which a keyboard never sees.
      <Tooltip
        content={
          <>
            <span className="font-semibold text-ink">{role}</span>: {shown}
            <span className="mt-0.5 block text-ink-3">{state.note}</span>
          </>
        }
        side="bottom"
      >
        <Link
          to="/settings"
          aria-label={`${role} model: ${shown} — ${state.note}`}
          className={cn(
            railControl,
            "min-w-0 gap-1.5 font-mono text-[11px]",
            // Stacked means the drawer, which is a page surface rather than the rail.
            stacked && cn("justify-start", pageControl),
          )}
        >
          <StatusDot tone={state.tone} pulse={state.pulse} />
          <span className="sr-only">{role}</span>
          {/* The cap belongs to the ground, not to the component. In the rail there is one
              line of a 48px bar to spend and 9rem is the whole point; in the drawer the rows
              run down a 320px track with nothing competing for the width, and cutting a model
              id there hands the rest to a tooltip a finger cannot open. A model id is a
              qualified name with no break opportunity, which is what `wrap-anywhere` is for.

              The rail's cap has a floor under it as well. The chips were the only thing in the
              bar allowed to shrink, so between `lg` and the width the bar actually wants they
              absorbed the whole squeeze and showed a dot and two characters — the two elements
              added at that breakpoint precisely so something named the models. 6rem still
              prints `claude-sonnet…`; the nav scrolls instead, which is what it now does. */}
          <span
            aria-hidden="true"
            className={cn(stacked ? "wrap-anywhere" : "min-w-[6rem] max-w-[9rem] truncate")}
          >
            {shown}
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
                  "relative flex min-h-11 items-center gap-2.5 rounded-sm px-2.5 text-sm transition",
                  "hover:bg-sunken hover:text-ink",
                  // "You are here" is an edge and a weight, never a fill. The current row used
                  // to be `bg-sunken text-ink` and every other row's hover was the same two
                  // classes, so while a finger rested anywhere in the list two of the six read
                  // as current — and with the pointer away the marker was a 1.19:1 wash. The
                  // fill is now the hover alone, which is the one job `--sunken` has on a row,
                  // and the current row is marked the way a docket row states its verdict: a
                  // left edge, read without being looked at and costing no horizontal space.
                  isActive
                    ? "font-semibold text-ink before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:bg-ink"
                    : "font-medium text-ink-2",
                )
              }
            >
              {/* The icon takes the row's own ink rather than a percentage of it. It used to
                  carry the state at `opacity-70`, which is a second, weaker copy of what the
                  ink tier beside it already says — and dimming is not a state, it is the same
                  state drawn less well. */}
              <>
                <item.icon className="size-4" />
                {item.label}
              </>
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    // Tighter than the `gap-4` between the drawer's own blocks, because that is the
    // relationship: Review and Workspace are two halves of one nav, and the nav is one of four
    // things in the sheet. At `gap-5` they were further apart from each other than the whole
    // nav was from the workspace path underneath it.
    <nav aria-label="Sections" className="grid gap-3.5">
      {group("Review", REVIEW_NAV)}
      {group("Workspace", WORKSPACE_NAV)}
    </nav>
  );
}

function WorkspacePath() {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  // The path wraps rather than truncates, and it is the surface that decides that. This
  // drawer exists below `lg` — phones and tablets — and the full value used to be behind a
  // `title`, which `ui/tooltip.tsx` argues at length never appears for a keyboard and never
  // appears at all under a finger. So on the one device this component was written for, the
  // fact it exists to carry was unreachable. There is vertical room in a drawer and no other
  // claim on it, and a path somebody can read is worth two lines; `wrap-anywhere` is what
  // gives an absolute path a break opportunity it does not otherwise have.
  //
  // `p-2` with the label inset by `px-1`, so this box and the Models box below it put their
  // labels and their content on one optical edge instead of two.
  return (
    <div className="min-w-0 rounded-md border border-rule bg-surface-2 p-2">
      <Label className="px-1 pb-1">Workspace</Label>
      <div className="min-w-0 px-1 font-mono text-[11px] leading-5 text-ink-2 wrap-anywhere">
        {workspace.isPending
          ? "reading…"
          : workspace.isError
            ? "could not read the workspace"
            : workspace.data?.workspace || "not recorded"}
      </div>
      {workspace.data?.hosted ? (
        <div className="mt-2 px-1 text-[11px] leading-4 text-ink-3">
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
      {/* The band's own two colours, because this lands on the rail rather than on the page.
          It is positioned at 16px/16px, which puts it inside the 48px bar — so in light theme
          its plate was `--ink` #0a0a0a over `--band` #0a0a0a, the same value, and what a
          keyboard user saw was white text and a white ring floating over the hamburger with no
          chip under it at all. The ring was fixed for this ground once and the plate behind it
          was not: `--band-ink` on `--band` is 18.95:1 in both themes, and it is the recipe the
          New review link at the other end of the bar already uses.

          The landing page's own skip link is left alone — it lands on the canvas, where
          `bg-ink` is the right plate. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-sm focus:bg-band-ink focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-band focus-visible:outline-band-ink"
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

          {/* One mark, drawn by the one file allowed to draw it. The rail used to build a
              second wordmark out of the bare compass glyph, so the product's identity was a
              32px deep-red tile on the landing page and an 18px white outline one click later
              — and the accent, which `design-system.md` names the brand mark as one of exactly
              four jobs for, appeared nowhere in the workbench at all. `BrandMark` is imported
              rather than copied because `ui/brand.tsx` is on the accent allowlist and this file
              is not: naming the accent fill here would fail the build, which is the point.

              24px rather than the landing page's 32: the tile is the identity, its size is a
              fact about the row it sits in, and a 48px bar cannot hold 32. The wordtext is now
              `font-display` so the two marks are one recipe at two sizes.

              Below `sm` the mark stands alone. The wordtext costs about a third of a 390px bar
              to repeat what the tab title says, and that width is what the primary action was
              being dropped for. `group-hover` on the mark is the same gesture `Wordmark`
              makes, so the two behave alike as well as read alike — it was the only control in
              the bar that cancelled its own hover and offered nothing in its place. */}
          <Link
            to="/"
            className={cn(railControl, "group shrink-0 gap-2 px-2 text-band-ink hover:bg-transparent")}
          >
            <BrandMark className="size-6 transition group-hover:scale-[1.04]" />
            <span className="hidden font-display text-[14px] font-bold tracking-tight sm:inline">
              <span className="font-normal text-band-ink-2">Arch</span>Compass
            </span>
          </Link>

          {/* `min-w-0` and a scroller, because a line of six labels in a 48px bar cannot wrap
              and must not be squeezed. The links were the first thing flex took width from, so
              at 1024 they lost their padding while the current item kept its fill and ended up
              touching the label beside it. They hold their shape now; where the bar is
              over-subscribed the nav scrolls, which is the same answer `ui/tabs.tsx` reaches
              for the same problem. */}
          <nav
            aria-label="Primary"
            className="scrollbar-none ml-2 hidden min-w-0 items-center gap-0.5 overflow-x-auto lg:flex"
          >
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    railControl,
                    "shrink-0 whitespace-nowrap",
                    // An underline, never a container. The fill was white at 10% over the
                    // band — #222222, which is 1.24:1 against the bar — and the hover state
                    // was the same fill at 8%, so while the pointer rested anywhere in the nav
                    // two items looked alike and with it away the current one was barely a
                    // shape. `--band-ink` on `--band` is 18.97:1, so the underline is not in
                    // doubt, and the hover keeps the fill as its own separate gesture.
                    isActive &&
                      "text-band-ink after:absolute after:inset-x-2.5 after:bottom-0 after:h-0.5 after:bg-band-ink",
                  )
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

              It gives its width back below `xl` and keeps only the icon. The word went with
              the key cap: at 1024 it was rendering as "Search.." — a control clipping its own
              label, which reads as a fault rather than as a control — and the chips beside it
              are what a reader checks without meaning to. A 13rem box holding one word nobody
              has typed into yet is not worth the workspace's identity disappearing for it. */}
          <button
            type="button"
            onClick={palette.open}
            aria-label="Search everything"
            className={cn(
              railControl,
              "min-w-0 gap-2 border border-band-rule text-band-ink-2 xl:min-w-[13rem] xl:justify-start",
            )}
          >
            <SearchIcon className="size-4 shrink-0" />
            <span className="hidden xl:inline">Search…</span>
            <KeyCap on="band" aria-hidden="true" className="ml-auto hidden xl:inline-flex">
              ⌘K
            </KeyCap>
          </button>

          {/* A rule between the places you can go and the facts about the workspace. Eleven
              controls in the bar wear one recipe, so "Policies" — somewhere to go — and
              `claude-sonnet-4-5` — a fact that happens to be clickable — read as the same kind
              of thing, and the only device separating the two halves was an invisible spacer.
              `--band-rule` is the band's own hairline, which is the structural device this
              system reaches for before it reaches for a fill. */}
          <span aria-hidden="true" className="mx-1 hidden h-5 w-px shrink-0 bg-band-rule lg:block" />

          {/* `lg`, which is where the hamburger goes. The two used to be `lg:hidden` and
              `xl:flex`, so between 1024 and 1280 — an ordinary window width — there was no
              drawer to open and no chips, and nothing on any page said which repository root
              the workspace pointed at or which two models it ran. */}
          <ModelChips className="hidden lg:flex" />
          {hasKeyboard ? <ShortcutsButton onOpen={shortcuts.open} /> : null}
          <ThemeToggle />
          {/* At every width, including the phone. It was `sm:inline-flex`, so below 640 the
              bar held a hamburger, a wordmark, a magnifier and a theme glyph and the product's
              primary action was two taps away inside the drawer under a group heading. The
              room it needs is what the wordtext beside the mark gives back. */}
          <Link
            to="/start"
            className="ml-1 inline-flex min-h-9 shrink-0 items-center rounded-sm bg-band-ink px-3 text-[13px] font-semibold text-band transition hover:opacity-90 focus-visible:outline-band-ink"
          >
            New review
          </Link>
        </div>
      </header>

      {/* A workspace route is handed the viewport and lays itself out inside it; a document
          route gets the measured column — and it is now the *same* measure the review page
          draws itself in, twelve times over. This box was 1560px, so moving from `/reviews` to
          a review on a wide monitor narrowed the content by 344px and jumped the gutters while
          the bar above stayed full-bleed: three measures on one screen, none of them explained
          by anything the reader could see. The two widest document pages, repositories and
          policies, are a main column beside a ~300px rail and both fit inside 76rem. */}
      <main
        id="main"
        tabIndex={-1}
        className={cn("min-w-0 outline-none", workspace && "flex min-h-0 flex-1 flex-col")}
      >
        {workspace ? (
          children
        ) : (
          <div className="mx-auto w-full max-w-[76rem] px-4 py-6 sm:px-6 sm:py-8">{children}</div>
        )}
      </main>

      <Drawer
        open={navOpen}
        onClose={() => setNavOpen(false)}
        // Named for what it holds, not for the product. The dialog announced itself as
        // "ArchCompass" with "Review workbench" under it — two lines of branding at the top of
        // the one surface that exists to say where you can go, and no word shared with the
        // control that opened it ("Open navigation") or the landmark inside it ("Sections").
        // The brand keeps a line; it does not take the heading.
        side="left"
        title="Navigation"
        description="ArchCompass · review workbench"
      >
        <div className="grid min-w-0 gap-4 p-3">
          <DrawerNav onNavigate={() => setNavOpen(false)} />
          <WorkspacePath />
          {/* The drawer is where the workspace says what it is, so the chips belong here
              too — which is what `stacked` was written for. It had no call site at all,
              so below the rail's own breakpoint nothing named the two models anywhere. */}
          <div className="min-w-0 rounded-md border border-rule bg-surface-2 p-2">
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
