import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { coreApi } from "../api";
import { cn } from "../lib/cn";
import { useTheme } from "../lib/theme";
import { StatusDot } from "../ui/badge";
import { Button, ButtonLink } from "../ui/button";
import { Wordmark } from "../ui/brand";
import { Drawer } from "../ui/drawer";
import {
  BookIcon,
  CaseIcon,
  FolderIcon,
  LayersIcon,
  MenuIcon,
  MonitorIcon,
  MoonIcon,
  PlayIcon,
  SlidersIcon,
  SunIcon,
} from "../ui/icons";

type NavItem = { to: string; label: string; icon: typeof PlayIcon; end?: boolean };

const REVIEW_NAV: NavItem[] = [
  { to: "/start", label: "Start a review", icon: PlayIcon },
  { to: "/reviews", label: "Reviews", icon: LayersIcon },
];

const WORKSPACE_NAV: NavItem[] = [
  { to: "/repositories", label: "Repositories", icon: FolderIcon },
  { to: "/cases", label: "Architecture cases", icon: CaseIcon },
  { to: "/policies", label: "Policies", icon: BookIcon },
  { to: "/settings", label: "Models", icon: SlidersIcon },
];

function NavGroup({
  label,
  items,
  onNavigate,
}: {
  label: string;
  items: NavItem[];
  onNavigate?: () => void;
}) {
  return (
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
                  "flex min-h-9 items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition",
                  isActive
                    ? "bg-accent-soft text-accent"
                    : "text-ink-2 hover:bg-sunken hover:text-ink",
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
}

function ThemeToggle() {
  const { preference, cycle } = useTheme();
  const Glyph = preference === "light" ? SunIcon : preference === "dark" ? MoonIcon : MonitorIcon;
  const next = preference === "system" ? "light" : preference === "light" ? "dark" : "system";
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={cycle}
      title={`Theme: ${preference}. Switch to ${next}.`}
      aria-label={`Theme: ${preference}. Switch to ${next}.`}
      className="px-2"
    >
      <Glyph className="size-4" />
    </Button>
  );
}

/** Reasoning and embedding, side by side, because they are two independent choices. */
function ModelChips({ className }: { className?: string }) {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: coreApi.workspace });
  const reasoning = workspace.data?.models.reasoning;
  const embedding = workspace.data?.models.embedding;
  const chip = (role: string, value: string | undefined, pinned: boolean | undefined) => (
    <Link
      to="/settings"
      className="group inline-flex min-w-0 items-center gap-2 rounded-md border border-rule bg-surface px-2.5 py-1.5 transition hover:border-rule-strong"
    >
      <StatusDot tone={value ? "cleared" : "held"} />
      <span className="min-w-0 text-left leading-tight">
        <span className="block text-[9px] font-bold uppercase tracking-[0.12em] text-ink-3">
          {role}
          {pinned ? " · pinned" : ""}
        </span>
        <span className="block max-w-[11rem] truncate font-mono text-[11px] text-ink-2 group-hover:text-ink">
          {value || "not selected"}
        </span>
      </span>
    </Link>
  );
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {chip("Reasoning", reasoning?.model, workspace.data?.models.pinned)}
      {chip("Embedding", embedding?.model, workspace.data?.models.embedding_pinned)}
    </div>
  );
}

function WorkspaceCard() {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: coreApi.workspace });
  // `truncate` sets `white-space: nowrap`, which makes the element's min-content width the
  // whole string — so without `min-w-0` on everything above it, a deep workspace path stops
  // being truncated and starts widening the sidebar instead. Truncation is a promise the
  // ancestors have to keep.
  return (
    <div className="min-w-0 rounded-md border border-rule bg-surface-2 p-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3">Workspace</div>
      <div
        title={workspace.data?.workspace}
        className="mt-1.5 truncate font-mono text-[11px] text-ink-2"
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

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-5">
      <nav aria-label="Primary" className="grid gap-5">
        <NavGroup label="Review" items={REVIEW_NAV} onNavigate={onNavigate} />
        <NavGroup label="Workspace" items={WORKSPACE_NAV} onNavigate={onNavigate} />
      </nav>
      <div className="mt-auto grid min-w-0 gap-3">
        <WorkspaceCard />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-on-accent"
      >
        Skip to content
      </a>

      <div className="lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
        <aside className="sticky top-0 hidden h-screen min-w-0 flex-col gap-5 overflow-hidden border-r border-rule bg-surface px-3 py-4 lg:flex">
          <div className="px-1.5">
            <Wordmark to="/" subtitle="Review workbench" />
          </div>
          <SidebarContent />
        </aside>

        <div className="min-w-0">
          <header className="sticky top-0 z-30 border-b border-rule bg-surface/85 backdrop-blur">
            <div className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
              <div className="flex min-w-0 items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="px-2 lg:hidden"
                  aria-label="Open navigation"
                  aria-expanded={navOpen}
                  onClick={() => setNavOpen(true)}
                >
                  <MenuIcon className="size-5" />
                </Button>
                <span className="lg:hidden">
                  <Wordmark to="/" />
                </span>
                <span className="hidden lg:block">
                  <Breadcrumb />
                </span>
              </div>
              <div className="flex items-center gap-2">
                <ModelChips className="hidden xl:flex" />
                <ThemeToggle />
                <ButtonLink to="/start" size="sm" className="hidden sm:inline-flex">
                  New review
                </ButtonLink>
              </div>
            </div>
          </header>

          <main id="main" tabIndex={-1} className="min-w-0 outline-none">
            <div className="mx-auto w-full max-w-[1560px] px-4 py-6 sm:px-6 sm:py-8">{children}</div>
          </main>
        </div>
      </div>

      <Drawer
        open={navOpen}
        onClose={() => setNavOpen(false)}
        side="left"
        title="ArchCompass"
        description="Review workbench"
      >
        <div className="p-3">
          <SidebarContent onNavigate={() => setNavOpen(false)} />
          <div className="mt-4 grid gap-2">
            <ModelChips className="flex-col items-stretch" />
          </div>
        </div>
      </Drawer>
    </div>
  );
}

const CRUMBS: Record<string, string> = {
  start: "Start a review",
  reviews: "Reviews",
  repositories: "Repositories",
  cases: "Architecture cases",
  policies: "Policies",
  settings: "Models",
};

function Breadcrumb() {
  const { pathname } = useLocation();
  const segments = pathname.split("/").filter(Boolean);
  if (!segments.length) return null;
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-ink-3">
      <Link to="/" className="hover:text-ink">
        Home
      </Link>
      {segments.map((segment, index) => {
        const to = `/${segments.slice(0, index + 1).join("/")}`;
        const last = index === segments.length - 1;
        const label = CRUMBS[segment] ?? segment;
        return (
          <span key={to} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="text-ink-3/50">
              /
            </span>
            {last ? (
              <span className={cn("text-ink-2", !CRUMBS[segment] && "font-mono")} aria-current="page">
                {label}
              </span>
            ) : (
              <Link to={to} className="hover:text-ink">
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
