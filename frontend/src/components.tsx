import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  BookOpenText,
  Boxes,
  Compass,
  Gauge,
  Menu,
  Monitor,
  Moon,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { api, ApiError } from "./api";
import { useTheme, type ThemePreference } from "./theme";

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

  return (
    <div className="theme-control" role="group" aria-label="Color theme">
      <span className="theme-control__label">Theme</span>
      <div className="theme-control__options">
        {themeOptions.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            className={preference === value ? "active" : ""}
            aria-label={`Use ${label.toLowerCase()} theme`}
            aria-pressed={preference === value}
            title={`${label}${value === "system" ? ` (${effectiveTheme})` : ""}`}
            onClick={() => setPreference(value)}
          >
            <Icon size={14} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function useDialogFocus(onClose: () => void, active = true) {
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!active) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previous = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const focusable = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), details > summary, [tabindex]:not([tabindex="-1"])',
        ),
      );
    focusable()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener("keydown", onKeyDown);
    return () => {
      dialog.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, [active, onClose]);

  return dialogRef;
}

export function Shell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  const navigation = [
    { to: "/", label: "Overview", icon: Gauge, end: true },
    { to: "/cases", label: "Cases", icon: Archive },
    { to: "/repositories", label: "Repositories", icon: Boxes },
    { to: "/reviews", label: "Reviews", icon: ShieldCheck },
    { to: "/policies", label: "Policies", icon: BookOpenText },
  ];

  return (
    <div className="app-shell">
      <button
        type="button"
        className="mobile-menu"
        aria-label={open ? "Close navigation" : "Open navigation"}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>
      <aside className={`sidebar ${open ? "sidebar--open" : ""}`}>
        <NavLink to="/" className="brand" onClick={() => setOpen(false)}>
          <span className="brand__mark"><Compass size={25} strokeWidth={1.7} /></span>
          <span>
            <strong>Arch Compass</strong>
            <small>Architecture fieldwork</small>
          </span>
        </NavLink>
        <nav className="nav" aria-label="Primary navigation">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setOpen(false)}
              className={({ isActive }) => `nav__item ${isActive ? "nav__item--active" : ""}`}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className={`status-dot ${workspace.isError ? "status-dot--error" : ""}`} />
          <div>
            <strong>{workspace.isError ? "Workspace unavailable" : "Local workspace"}</strong>
            <span title={workspace.data?.workspace}>
              {workspace.data?.workspace.split("/").at(-1) || "Loading…"}
            </span>
          </div>
          {workspace.data && (
            <p>
              {workspace.data.models.reasoning.provider} ·{" "}
              {workspace.data.models.reasoning.model}
            </p>
          )}
        </div>
      </aside>
      <main className="main">
        <header className="shell-toolbar">
          <span className="shell-toolbar__context">Local architecture workspace</span>
          <ThemeControl />
        </header>
        {children}
      </main>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "teal";
}) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function Loading({ label = "Reading workspace…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <Compass className="loading__compass" size={26} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorPanel({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError || error instanceof Error
      ? error.message
      : "Something went wrong while reading the workspace.";
  return (
    <div className="notice notice--error" role="alert">
      <strong>Couldn’t complete that request</strong>
      <p>{message}</p>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon">{icon || <Compass size={30} />}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function Stat({
  label,
  value,
  detail,
}: {
  label: string;
  value: ReactNode;
  detail?: string;
}) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
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
