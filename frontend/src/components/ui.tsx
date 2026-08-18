import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-rule bg-surface p-5 shadow-card ${className}`}>{children}</section>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === "completed" || status === "cleared"
    ? "bg-success/10 text-success"
    : status === "failed" || status === "material"
      ? "bg-danger/10 text-danger"
      : status === "cancelled"
        ? "bg-ink-3/10 text-ink-3"
        : "bg-primary/10 text-primary";
  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${tone}`}>{status.replaceAll("_", " ")}</span>;
}

export function PageTitle({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow ? <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{eyebrow}</p> : null}
        <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">{title}</h1>
      </div>
      {children}
    </header>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="rounded-xl border border-rule bg-surface p-8 text-sm text-ink-2">{label}</div>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  return <div role="alert" className="rounded-xl border border-danger/30 bg-danger/5 p-4 text-sm text-danger">{error instanceof Error ? error.message : String(error)}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-rule p-10 text-center text-sm text-ink-3">{children}</div>;
}

export function Metric({ label, value }: { label: string; value: ReactNode }) {
  return <div><div className="text-2xl font-semibold tabular-nums">{value}</div><div className="mt-1 text-xs uppercase tracking-wide text-ink-3">{label}</div></div>;
}

export function Tabs({ active, onChange, items }: { active: string; onChange: (tab: string) => void; items: Array<{ id: string; label: string; count?: number }> }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-rule" role="tablist">
      {items.map((item) => (
        <button key={item.id} role="tab" aria-selected={active === item.id} onClick={() => onChange(item.id)} className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium ${active === item.id ? "border-primary text-primary" : "border-transparent text-ink-2 hover:text-ink"}`}>
          {item.label}{item.count === undefined ? "" : ` ${item.count}`}
        </button>
      ))}
    </div>
  );
}
