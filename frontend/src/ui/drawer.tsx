import type { ReactNode } from "react";
import { useCallback, useEffect } from "react";

import { cn } from "../lib/cn";
import { useFocusTrap } from "../lib/motion";
import { Button } from "./button";

/**
 * A slide-over surface: navigation on a phone, the context rail on a tablet, a sheet from
 * the bottom where the content is a list of choices. One component, one behaviour —
 * Escape closes, focus is trapped, the page behind stops scrolling.
 */
export function Drawer({
  open,
  onClose,
  title,
  description,
  side = "right",
  children,
  footer,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  side?: "left" | "right" | "bottom";
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  const close = useCallback(() => onClose(), [onClose]);
  const ref = useFocusTrap(open, close);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex" role="presentation">
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        onClick={close}
        className="absolute inset-0 animate-fade bg-overlay"
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative flex max-h-full flex-col border-rule bg-surface shadow-float",
          side === "right" && "ml-auto h-full w-full max-w-[26rem] animate-slide-left border-l",
          side === "left" && "mr-auto h-full w-full max-w-[20rem] animate-slide-left border-r",
          side === "bottom" &&
            "mt-auto max-h-[85vh] w-full animate-slide-up rounded-t-xl border-t pb-[env(safe-area-inset-bottom)]",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-rule px-4 py-3.5">
          <div className="min-w-0">
            <h2 className="font-display text-base font-semibold tracking-tight">{title}</h2>
            {description ? <p className="mt-0.5 text-xs text-ink-3">{description}</p> : null}
          </div>
          <Button variant="ghost" size="sm" onClick={close} aria-label="Close panel">
            Close
          </Button>
        </div>
        <div className="scrollbar-slim min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {children}
        </div>
        {footer ? <div className="border-t border-rule px-4 py-3">{footer}</div> : null}
      </div>
    </div>
  );
}
