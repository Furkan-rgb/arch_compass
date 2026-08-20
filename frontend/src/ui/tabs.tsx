import type { ReactNode } from "react";
import { useRef } from "react";

import { cn } from "../lib/cn";

export type TabItem = { id: string; label: string; count?: number };

/**
 * A tablist with arrow-key roving focus, because a workbench is driven from the keyboard as
 * often as from the pointer.
 */
export function Tabs({
  items,
  active,
  onChange,
  label,
  className,
  variant = "line",
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  label: string;
  className?: string;
  variant?: "line" | "solid";
}) {
  const listRef = useRef<HTMLDivElement | null>(null);

  function onKeyDown(event: React.KeyboardEvent) {
    const index = items.findIndex((item) => item.id === active);
    if (index === -1) return;
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = items[(index + step + items.length) % items.length];
    onChange(next.id);
    listRef.current?.querySelector<HTMLButtonElement>(`#tab-${next.id}`)?.focus();
  }

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cn(
        "scrollbar-none flex gap-1 overflow-x-auto",
        variant === "line" ? "border-b border-rule" : "rounded-md border border-rule bg-surface p-1",
        className,
      )}
    >
      {items.map((item) => {
        const selected = item.id === active;
        return (
          <button
            key={item.id}
            id={`tab-${item.id}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={`panel-${item.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-sm font-semibold transition",
              variant === "line"
                ? cn(
                    "-mb-px border-b-2 px-3 py-2.5",
                    selected
                      ? "border-ink text-ink"
                      : "border-transparent text-ink-3 hover:border-rule-strong hover:text-ink",
                  )
                : cn(
                    "min-h-8 rounded-sm px-3",
                    selected ? "bg-ink text-canvas" : "text-ink-3 hover:bg-sunken hover:text-ink",
                  ),
            )}
          >
            {item.label}
            {item.count === undefined ? null : (
              <span
                className={cn(
                  "rounded-xs px-1.5 py-0.5 text-[10px] font-bold tabular-nums",
                  selected && variant === "solid"
                    ? "bg-canvas/20 text-canvas"
                    : "bg-sunken text-ink-3",
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  id,
  active,
  children,
  className,
}: {
  id: string;
  active: string;
  children: ReactNode;
  className?: string;
}) {
  if (id !== active) return null;
  return (
    <div
      id={`panel-${id}`}
      role="tabpanel"
      aria-labelledby={`tab-${id}`}
      tabIndex={0}
      className={cn("animate-fade outline-none", className)}
    >
      {children}
    </div>
  );
}
