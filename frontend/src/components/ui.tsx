import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export const controlClass =
  "w-full rounded-xl border border-rule-strong bg-surface px-3.5 py-2.5 text-sm text-ink shadow-sm outline-none transition placeholder:text-ink-3 focus:border-primary focus:ring-4 focus:ring-primary/10 disabled:cursor-not-allowed disabled:opacity-55";

const buttonVariants = {
  primary: "border border-primary bg-primary text-on-accent shadow-sm hover:border-primary-strong hover:bg-primary-strong",
  secondary: "border border-rule-strong bg-surface text-ink shadow-sm hover:border-primary/40 hover:bg-primary-soft",
  ghost: "border border-transparent text-ink-2 hover:bg-canvas-strong hover:text-ink",
  danger: "border border-danger/25 bg-danger-soft text-danger hover:border-danger/40 hover:bg-danger/10",
} as const;

export function buttonClass(variant: keyof typeof buttonVariants = "primary", size: "sm" | "md" = "md") {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-xl font-semibold outline-none transition focus-visible:ring-4 focus-visible:ring-primary/15 disabled:pointer-events-none disabled:opacity-45",
    size === "sm" ? "min-h-9 px-3 py-1.5 text-xs" : "min-h-11 px-4 py-2.5 text-sm",
    buttonVariants[variant],
  );
}

export function Button({ className, variant = "primary", size = "md", type = "button", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof buttonVariants; size?: "sm" | "md" }) {
  return <button type={type} className={cn(buttonClass(variant, size), className)} {...props} />;
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(controlClass, className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(controlClass, "min-h-28 resize-y leading-6", className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(controlClass, className)} {...props} />;
}

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor?: string; children: ReactNode }) {
  return <div><label htmlFor={htmlFor} className="block text-sm font-semibold text-ink">{label}</label>{hint ? <p className="mt-1 text-xs leading-5 text-ink-3">{hint}</p> : null}<div className="mt-2">{children}</div></div>;
}

export function Card({ children, className = "", tone = "default" }: { children: ReactNode; className?: string; tone?: "default" | "subtle" | "accent" }) {
  return <section className={cn("rounded-2xl border p-5 sm:p-6", tone === "default" && "border-rule bg-surface shadow-card", tone === "subtle" && "border-rule bg-canvas-strong/60", tone === "accent" && "border-primary/20 bg-primary-soft", className)}>{children}</section>;
}

const positive = new Set(["completed", "cleared", "available", "accept", "selected"]);
const negative = new Set(["failed", "material", "unavailable", "waive"]);
const neutral = new Set(["cancelled", "addressed", "skipped"]);
const warning = new Set(["held", "awaiting_answers", "park", "required"]);

export function StatusBadge({ status }: { status: string }) {
  const tone = positive.has(status) ? "border-success/20 bg-success-soft text-success" : negative.has(status) ? "border-danger/20 bg-danger-soft text-danger" : warning.has(status) ? "border-warning/25 bg-warning-soft text-warning" : neutral.has(status) ? "border-rule-strong bg-canvas-strong text-ink-2" : "border-primary/20 bg-primary-soft text-primary";
  return <span className={cn("inline-flex rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.1em]", tone)}>{status.replaceAll("_", " ")}</span>;
}

export function PageTitle({ eyebrow, title, description, children }: { eyebrow?: string; title: string; description?: string; children?: ReactNode }) {
  return <header className="mb-7 flex flex-col justify-between gap-5 border-b border-rule pb-6 sm:flex-row sm:items-end"><div className="min-w-0">{eyebrow ? <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary">{eyebrow}</p> : null}<h1 className="mt-1 max-w-4xl font-display text-3xl font-semibold tracking-[-0.035em] text-ink sm:text-4xl">{title}</h1>{description ? <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-2">{description}</p> : null}</div>{children ? <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div> : null}</header>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div role="status" className="rounded-2xl border border-rule bg-surface p-8 shadow-card"><div className="flex items-center gap-3 text-sm font-medium text-ink-2"><span className="size-4 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />{label}</div></div>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  return <div role="alert" className="rounded-xl border border-danger/25 bg-danger-soft p-4 text-sm leading-6 text-danger"><strong className="block font-semibold">Something needs attention</strong>{error instanceof Error ? error.message : String(error)}</div>;
}

export function Empty({ title = "Nothing here yet", children }: { title?: string; children: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-rule-strong bg-surface/50 px-6 py-14 text-center"><div className="font-display text-lg font-semibold text-ink">{title}</div><div className="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-3">{children}</div></div>;
}

export function Metric({ label, value, detail }: { label: string; value: ReactNode; detail?: string }) {
  return <div className="min-w-0"><div className="font-display text-2xl font-semibold tabular-nums text-ink">{value}</div><div className="mt-1 text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3">{label}</div>{detail ? <div className="mt-1 text-xs text-ink-3">{detail}</div> : null}</div>;
}

export function Tabs({ active, onChange, items, ariaLabel = "Sections" }: { active: string; onChange: (tab: string) => void; items: Array<{ id: string; label: string; count?: number }>; ariaLabel?: string }) {
  return <div className="scrollbar-none flex gap-1 overflow-x-auto rounded-xl border border-rule bg-surface p-1.5 shadow-sm" role="tablist" aria-label={ariaLabel}>{items.map((item) => <button key={item.id} id={`tab-${item.id}`} role="tab" aria-controls={`panel-${item.id}`} aria-selected={active === item.id} onClick={() => onChange(item.id)} className={cn("inline-flex min-h-9 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-semibold outline-none transition focus-visible:ring-2 focus-visible:ring-primary/30", active === item.id ? "bg-primary text-on-accent shadow-sm" : "text-ink-2 hover:bg-canvas-strong hover:text-ink")}>{item.label}{item.count === undefined ? null : <span className={cn("rounded-full px-1.5 py-0.5 text-[10px]", active === item.id ? "bg-white/18" : "bg-canvas-strong text-ink-3")}>{item.count}</span>}</button>)}</div>;
}

export function SectionHeading({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-display text-xl font-semibold tracking-tight text-ink">{title}</h2>{description ? <p className="mt-1 text-sm leading-6 text-ink-3">{description}</p> : null}</div>{children}</div>;
}
