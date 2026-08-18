import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { coreApi } from "../api";

const navigation = [
  ["/start", "Start"],
  ["/reviews", "Reviews"],
  ["/repositories", "Repositories"],
  ["/cases", "Cases"],
  ["/policies", "Policies"],
  ["/settings", "Models"],
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: coreApi.workspace });
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-rule bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-7 px-5 py-3.5">
          <NavLink to="/start" className="font-display text-xl font-semibold tracking-tight">ArchCompass</NavLink>
          <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
            {navigation.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => `rounded-md px-3 py-2 text-sm ${isActive ? "bg-primary/10 font-medium text-primary" : "text-ink-2 hover:bg-canvas hover:text-ink"}`}>{label}</NavLink>
            ))}
          </nav>
          <div className="hidden text-right text-xs text-ink-3 md:block">
            <div>{workspace.data?.models.reasoning ? `${workspace.data.models.reasoning.provider} · ${workspace.data.models.reasoning.model}` : "No model selected"}</div>
            <div className="max-w-48 truncate">{workspace.data?.workspace}</div>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-5 py-8">{children}</main>
    </div>
  );
}
