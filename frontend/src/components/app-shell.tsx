import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { coreApi } from "../api";
import { cn } from "./ui";

const navigation = [
  { to: "/start", label: "New review", mark: "+" },
  { to: "/reviews", label: "Reviews", mark: "R" },
  { to: "/repositories", label: "Repositories", mark: "⌘" },
  { to: "/cases", label: "Cases", mark: "C" },
  { to: "/policies", label: "Policies", mark: "P" },
  { to: "/settings", label: "Models", mark: "M" },
] as const;

function Navigation({ compact = false }: { compact?: boolean }) {
  return (
    <nav aria-label="Primary" className={cn(compact ? "scrollbar-none flex gap-1 overflow-x-auto px-4 py-2" : "grid gap-1")}>
      {navigation.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) => cn(
            "group flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm font-semibold outline-none transition focus-visible:ring-2 focus-visible:ring-primary/30",
            compact && "shrink-0",
            isActive ? "bg-primary text-on-accent shadow-sm" : "text-ink-2 hover:bg-canvas-strong hover:text-ink",
          )}
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-lg border border-current/15 text-[11px] font-bold opacity-80">{item.mark}</span>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: coreApi.workspace });
  const reasoning = workspace.data?.models.reasoning;
  const embedding = workspace.data?.models.embedding;

  return (
    <div className="min-h-screen bg-canvas text-ink lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="hidden min-h-screen border-r border-rule bg-surface lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
        <div className="border-b border-rule px-6 py-6">
          <NavLink to="/start" className="group block rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary/30">
            <div className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-xl bg-primary font-display text-lg font-bold text-on-accent shadow-sm">A</span>
              <div><div className="font-display text-lg font-semibold tracking-tight">ArchCompass</div><div className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink-3">Review workspace</div></div>
            </div>
          </NavLink>
        </div>
        <div className="flex-1 px-3 py-5"><Navigation /></div>
        <div className="m-3 rounded-2xl border border-rule bg-canvas p-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3">Runtime</div>
          <div className="mt-3 grid gap-2.5 text-xs">
            <div><div className="text-ink-3">Reasoning</div><div className="mt-0.5 truncate font-medium text-ink">{reasoning ? reasoning.model : "Not selected"}</div></div>
            <div><div className="text-ink-3">Embeddings</div><div className="mt-0.5 truncate font-medium text-ink">{embedding ? embedding.model : "Not selected"}</div></div>
          </div>
          <div className="mt-3 truncate border-t border-rule pt-3 font-mono text-[10px] text-ink-3" title={workspace.data?.workspace}>{workspace.data?.workspace || "Loading workspace…"}</div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-rule bg-surface/95 backdrop-blur lg:hidden">
          <div className="flex items-center justify-between px-5 py-3">
            <NavLink to="/start" className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight"><span className="grid size-7 place-items-center rounded-lg bg-primary text-sm text-on-accent">A</span>ArchCompass</NavLink>
            <div className="max-w-36 truncate text-right text-[10px] text-ink-3">{reasoning?.model || "Configure models"}</div>
          </div>
          <Navigation compact />
        </header>
        <main className="mx-auto w-full max-w-[1500px] px-4 py-6 sm:px-6 sm:py-8 xl:px-10">{children}</main>
      </div>
    </div>
  );
}
