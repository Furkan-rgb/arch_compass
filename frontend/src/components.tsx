import { useQuery } from "@tanstack/react-query";
import { Compass, Monitor, Moon, Sun } from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

import { api, ApiError } from "./api";
import { CommandPalette } from "./command-palette";
import { isThemePreference, useTheme, type ThemePreference } from "./theme";

const themeOptions: Array<{
  value: ThemePreference;
  label: string;
  icon: typeof Monitor;
}> = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function ThemeControl() {
  const { preference, effectiveTheme, setPreference } = useTheme();

  // Three icons in a 48px bar: the label each button carried is what the tooltip and the
  // accessible name already say, and saying it a third time cost the width of a control.
  //
  // A toggle group rather than three buttons, because that is what this is: one of three,
  // and exactly one is already true. It announces itself as a radio group, which is the
  // difference between "three things you may press" and "a setting with three values".
  return (
    <ToggleGroup
      type="single"
      value={preference}
      // A group in single mode clears itself when the current item is pressed again. A
      // theme is never unset, so the empty value is the one answer this control refuses.
      onValueChange={(value) => {
        if (isThemePreference(value)) setPreference(value);
      }}
      aria-label="Color theme"
    >
      {themeOptions.map(({ value, label, icon: Icon }) => (
        <ToggleGroupItem
          key={value}
          value={value}
          // Square, and a step quieter than the group's own default: an icon lays down more
          // ink per pixel than a word does, and at 13px in the second ink these three read
          // as loud as the navigation beside them.
          className="w-6 px-0 text-ink-3"
          aria-label={`Use ${label.toLowerCase()} theme`}
          title={`${label}${value === "system" ? ` (${effectiveTheme})` : ""}`}
        >
          <Icon size={13} aria-hidden="true" />
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/**
 * The page column every route is drawn in.
 *
 * A class string rather than a component, because what it says is one measurement and two
 * paddings, and every caller wants to add its own to them. `cn` resolves the overlaps, so a
 * page that ends closer to the fold writes `pb-6` and nothing else.
 */
export const page = "mx-auto w-[min(1400px,100%)] px-[var(--gutter)] pt-[26px] pb-[30px]";

/**
 * The one sheet. Every region of every page is this and nothing else — an edge, a radius, the
 * surface and one step of depth — so depth never has to be spent twice on one thing.
 *
 * Its edge is a token because that is the part the theme moves: by day the panel floats on
 * the canvas and its shadow is what separates it, so it draws no rule at all; by night a
 * shadow cannot read on onyx, so the same panel gets a hairline instead. Same radius, same
 * surface, same padding — only the material changes.
 *
 * Lowercase, and deliberately not the vendored `Sheet`: that one is the drawer a document
 * opens in, which is the other thing shadcn calls a sheet. This is the flat panel a region of
 * a page sits on, and it has been called the sheet here since before the drawer existed.
 */
export const sheet =
  "mb-[var(--gap-lg)] rounded-panel [border:var(--sheet-border)] bg-surface shadow-card";

/**
 * A labelled division inside a region: what this part of it is, then the part itself.
 *
 * Shared because two surfaces divide themselves the same way for the same reason — the
 * conclusion's themes and its recommended order, and the questions a held run is asking.
 * The label is a heading so a long page is navigable, and it is the quietest heading on it:
 * a division of something the reader is already reading does not need to announce itself
 * louder than the sentences under it.
 */
export function Group({
  label,
  children,
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div data-slot="group" className={cn("mt-[var(--gap-lg)]", className)}>
      <h3 className="m-0 mb-2.5 font-display text-micro font-[650] tracking-[.09em] uppercase text-ink-3">
        {label}
      </h3>
      {children}
    </div>
  );
}

/**
 * Nothing here yet, in one line.
 *
 * The sibling of `EmptyState` for the places with no heading and no action to hang on one:
 * the explanation appears exactly when the reader needs to be told what would fill this, and
 * never once something has. A sentence on a dashed line, not a monument to absence.
 */
export function EmptyLine({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p
      data-slot="empty-line"
      className={cn(
        "m-0 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-control border border-dashed border-rule px-3.5 py-3 text-meta leading-[1.5] text-ink-3",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  // The navigation is the flow (master plan §6B): one entry for the flow itself, then the
  // two standing records it reads and writes — the policy corpus it judges against, and
  // every review it has produced. Repositories and cases are the start step's two rails,
  // not destinations beside it.
  const navigation = [
    { to: "/", label: "Start", end: true },
    { to: "/reviews", label: "Reviews" },
    { to: "/policies", label: "Policies" },
  ];
  const reasoning = workspace.data?.models.reasoning;

  return (
    <div className="min-h-screen">
      {/* The whole identity in 48px. It wraps rather than folding into a drawer: three
          links and a status chip fit on a phone, and a hamburger would hide the only
          thing on this bar the reader cannot work out for themselves. */}
      {/* `--chrome` is translucent now, so every surface painted with it blurs behind
          itself — without that the bar reads as a smear of whatever scrolls under it. */}
      <header className="sticky top-0 z-20 flex min-h-[52px] flex-wrap items-center gap-x-[18px] gap-y-1.5 border-b border-rule bg-chrome px-[var(--gutter)] py-2 backdrop-blur-[var(--chrome-blur)]">
        <NavLink to="/" className="mr-1 flex items-center gap-2">
          <span
            className="grid size-[26px] flex-none place-items-center rounded-sm bg-primary font-display text-meta font-bold text-on-accent"
            aria-hidden="true"
          >
            AC
          </span>
          <b className="font-display text-ui font-semibold tracking-[-.01em]">Arch Compass</b>
        </NavLink>
        <nav aria-label="Primary navigation" className="flex gap-0.5">
          {navigation.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "rounded-sm px-3 py-1.5 text-ui",
                  // The active pill is chrome rather than accent: it marks where you are,
                  // and the accent in this design means "you can act on this". By day that
                  // is a white chip lifted out of the translucent bar; by night the bar has
                  // no lighter step to give, so it is the accent at 13% instead.
                  isActive
                    ? "bg-[var(--chrome-active)] font-[550] text-[var(--chrome-active-ink)]"
                    : "text-ink-2 hover:bg-sunken hover:text-ink",
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="flex-1" />
        {/* The way to anything this workspace holds, and the keystroke that opens it. The
            hint is the control: a shortcut nobody is told about is a shortcut nobody has. */}
        <CommandPalette />
        {/* What this workspace is pointed at, in the face its values are stored in. It
            states itself rather than waiting to be asked: which model answered is the first
            thing a verdict's credibility depends on. Mono and unweighted, against the chip's
            own voice — this is a machine's name, not a judgement about anything. */}
        <Badge
          variant={workspace.isError ? "material" : "neutral"}
          className={cn(
            "min-w-0 gap-2 py-0.5 font-mono font-normal tracking-normal",
            // The bar is --chrome and a chip is --surface; in the dark theme those are two
            // different greys, so this one keeps the bar it sits on.
            !workspace.isError && "bg-transparent",
          )}
          title={workspace.data?.workspace}
        >
          <span
            className={cn(
              "size-1.5 flex-none rounded-full",
              workspace.isError ? "bg-danger" : "bg-cleared",
            )}
          />
          <span className="overflow-hidden text-ellipsis whitespace-nowrap">
            {workspace.isError
              ? "workspace unavailable"
              : reasoning
                ? `${reasoning.provider} · ${reasoning.model}`
                : "reading workspace…"}
          </span>
        </Badge>
        <ThemeControl />
      </header>
      <main className="min-h-[calc(100vh-52px)]">{children}</main>
    </div>
  );
}

/**
 * The context row: where the reader is, and what can be done here.
 *
 * It replaced a 58px display heading over an uppercase eyebrow and a standing paragraph —
 * about 200 vertical pixels of editorial before the first control, on every visit. A
 * breadcrumb states the same thing in one line and gives the parent record back as a link.
 */
export function PageHeader({
  title,
  parent,
  meta,
  action,
}: {
  title: string;
  parent?: { to: string; label: string };
  /** A fact about the record itself — the revision it is pinned to, say — beside its name. */
  meta?: ReactNode;
  action?: ReactNode;
}) {
  return (
    // A chrome bar rather than page content, so it bleeds back out through the page's own
    // gutter and its rule runs the width of the column.
    <header
      data-slot="page-header"
      className="mx-[calc(var(--gutter)*-1)] -mt-[26px] mb-[26px] flex min-h-[50px] flex-wrap items-center gap-x-3.5 gap-y-2 border-b border-rule bg-chrome px-[var(--gutter)] py-2 backdrop-blur-[var(--chrome-blur)]"
    >
      {/* Everything in the trail is quieter than the record's own name, whatever it is —
          the parent link, the separator, and any chip the caller hangs off the end. That
          last one is why this is a descendant rule and not three classes: `meta` is the
          caller's markup, and a verdict-loud chip has no business shouting in a breadcrumb. */}
      <div className="flex min-w-0 items-center gap-2 text-ui [&_a:hover]:text-ink-2 [&_a]:text-ink-3 [&_span]:text-ink-3">
        {parent && (
          <>
            <Link to={parent.to}>{parent.label}</Link>
            <span aria-hidden="true">/</span>
          </>
        )}
        <b className="overflow-hidden font-display text-read font-semibold tracking-[-.015em] text-ellipsis whitespace-nowrap">
          {title}
        </b>
        {meta}
      </div>
      <div className="flex-1" />
      {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
    </header>
  );
}

/**
 * Waiting, drawn as the rows that are coming.
 *
 * A spinner says only "something is happening"; a skeleton at the final density says what
 * is happening and reserves the space it will need, so nothing under the reader's pointer
 * moves when the data lands. `rows` is the shape the caller already knows — a list that
 * will hold three rows waits as three rows.
 *
 * The label is still announced, just not drawn: it repeated what the empty shapes below it
 * were already saying, and every list on every page said it at once.
 */
export function Loading({
  label = "Reading workspace…",
  rows = 3,
  className,
}: {
  label?: string;
  rows?: number;
  /** For the caller whose wait is not a list — a single row in a strip of pills, say. */
  className?: string;
}) {
  return (
    <div
      data-slot="skeleton-rows"
      role="status"
      className={cn("grid gap-2 p-3", className)}
    >
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          data-slot="skeleton-row"
          aria-hidden="true"
          // The rows that are coming, drawn as an outline rather than as the row's own
          // material: a white card standing in for a white card says nothing on porcelain.
          // The height is the modest one, because most of these stand in for a picker's
          // list rather than for a ledger; a caller waiting on 50px rows says so.
          className="grid min-h-[38px] grid-cols-[var(--stripe-col)_minmax(0,1fr)_72px] items-center gap-x-3.5 overflow-hidden rounded-control border border-rule-soft pr-[var(--row-pad-x)]"
        >
          <Skeleton className="h-full rounded-none bg-rule" />
          <Skeleton className={cn("h-2", nameWidths[index % nameWidths.length])} />
          <Skeleton className="h-2" />
        </div>
      ))}
    </div>
  );
}

/* Uneven, because names are uneven. Cycled rather than random so a re-render does not
   reshuffle the bars while someone is looking at them. */
const nameWidths = ["w-[55%]", "w-[46%]", "w-[68%]"];

/**
 * The one wait with nothing to draw the shape of: the app's own first paint, before any
 * route has been fetched and while the page is otherwise empty chrome.
 */
export function Booting({ label }: { label: string }) {
  return (
    <div className="booting" role="status">
      <Compass className="booting__compass" size={16} />
      <span>{label}</span>
    </div>
  );
}

/**
 * What went wrong, and — where this page actually knows one — what to do about it.
 *
 * No apology and no restatement of the request that failed: the reader watched themselves
 * make it. The server's own words are kept verbatim, because a validator naming the field
 * it rejected tells someone more than any paraphrase of it could.
 */
export function ErrorPanel({ error }: { error: unknown }) {
  // The one failure whose fix is knowable from here. `fetch` reports an unreachable server
  // as a TypeError whose message ("Failed to fetch") names neither the cause nor the cure.
  const unreachable = error instanceof TypeError;
  const what = unreachable
    ? "The workspace didn’t answer."
    : error instanceof ApiError || error instanceof Error
      ? error.message
      : "The workspace sent back something this page could not read.";
  // A failure borrows the revision family — the hue that already means "this should change" —
  // rather than bringing a fourth colour onto the screen. Bold says what happened; the plain
  // half says what to do about it. Neither apologises.
  return (
    <p
      data-slot="error-strip"
      role="alert"
      className="my-2.5 flex flex-wrap gap-x-1.5 gap-y-0.5 rounded-control border border-danger-rule border-l-[3px] border-l-danger bg-danger-soft px-3.5 py-2.5 text-meta leading-[1.5] [&_code]:text-micro"
    >
      <b className="font-[650] text-danger">{what}</b>
      {unreachable ? (
        <span className="text-ink-2">
          Check that <code>archcompass web</code> is still running, then try again.
        </span>
      ) : null}
    </p>
  );
}

/**
 * Nothing here yet, in one line.
 *
 * It replaced a 260px panel built around an icon in a circle — a decorated announcement
 * that the thing you came for does not exist. What a reader needs is the sentence that
 * says what would fill this and the control that starts filling it, on the line where the
 * rows will appear.
 */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-control border border-dashed border-rule px-3.5 py-3 text-meta leading-[1.5] text-ink-3 [&_code]:text-micro">
      <h3 className="m-0 text-meta font-[650] tracking-normal text-ink-2">{title}</h3>
      <p className="m-0 max-w-[72ch]">{description}</p>
      {action}
    </div>
  );
}

export function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function shortId(value: string) {
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-5)}` : value;
}

/* Machine names — edge kinds, policy scopes, lenses — reach the screen as they are stored.
   Reading them is the caller's problem, not the stylesheet's: a CSS transform would leave
   the underscores in place and recase anything the backend meant literally. */
export function humanizeLabel(value: string) {
  const words = value.replaceAll("_", " ").replaceAll("-", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
