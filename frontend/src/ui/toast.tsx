import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cn } from "../lib/cn";
import { Notice } from "./states";

/**
 * A save that worked and a save that failed used to look the same from a distance.
 *
 * The only success signal in the product was a `sr-only` live region, so a sighted reviewer
 * saw nothing at all — and a mutation that lands off screen (a policy saved, a model chosen,
 * a case created) confirmed nothing to anybody. Errors were handled well but only *in place*,
 * which is the same gap from the other side: a failure two panels above where you are
 * looking is invisible.
 *
 * Built from `Notice` rather than as a new surface, which settles the colour question before
 * it is asked. `Notice` has two tones and neither is a hue: `notice` is a fact that recedes,
 * `working` is the workspace acting or asking and is emphasised in ink. A toast is one of
 * those two things, so it needs no third tone and no accent — and a red toast for a failed
 * request would be spending the one hue the product has on chrome that is about to leave.
 */
type Tone = "notice" | "working";

export type Toast = { id: number; tone: Tone; title?: string; message: ReactNode };

type ToastApi = {
  /** Something worked. Recedes, and goes on its own. */
  say: (message: ReactNode, title?: string) => void;
  /** Something did not. Stays in ink, and stays put until it is dismissed. */
  warn: (message: ReactNode, title?: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

/**
 * Six seconds for a confirmation, and no timer at all for a failure.
 *
 * A confirmation is a receipt: it is read at a glance or not at all, and one that lingers
 * becomes a thing to dismiss. A failure is the opposite — the reader may be looking
 * somewhere else entirely when it lands, and a message that removed itself before they
 * turned round would be worse than no message.
 */
const DWELL_MS = 6_000;

/**
 * Silent outside a provider, rather than fatal.
 *
 * The application mounts one provider at the root and never unmounts it, so the only place
 * this fallback is ever reached is a test rendering one component on its own — and a test
 * harness that swallows a confirmation is exactly right. Throwing would make every existing
 * component test fail the day its component learns to say "saved", which is a cost paid by
 * the wrong people for a mistake that cannot happen in the product.
 */
const SILENT: ToastApi = { say: () => {}, warn: () => {} };

export function useToast(): ToastApi {
  return useContext(ToastContext) ?? SILENT;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (tone: Tone, message: ReactNode, title?: string) => {
      const id = (next.current += 1);
      // Three at a time. A stack that grows without limit covers the thing it is reporting
      // on, and the oldest is the one already read.
      setToasts((current) => [...current.slice(-2), { id, tone, title, message }]);
      if (tone === "notice") {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), DWELL_MS),
        );
      }
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending.values()) clearTimeout(timer);
      pending.clear();
    };
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      say: (message, title) => push("notice", message, title),
      warn: (message, title) => push("working", message, title),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

/**
 * One live region around the whole stack, not one per toast.
 *
 * A region announces what changes *inside* it, so a region that is created at the same
 * moment as its content is a region a screen reader may never read. The container is
 * mounted for the life of the application and empty most of the time; what arrives in it is
 * what gets announced.
 *
 * `polite`, and never `assertive`: every one of these follows something the reader just did,
 * so none of them is worth interrupting a sentence being read.
 */
function ToastStack({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div
      role="status"
      aria-live="polite"
      // `role="status"` carries an implicit `aria-atomic="true"`, so a change anywhere in the
      // region has assistive technology read the region entire. With three toasts held at
      // once, a reviewer taking three decisions in a row heard the first message again, then
      // the first two again, then all three — each with the word "Dismiss" after it. Only what
      // arrives is worth reading; the ones already announced were already announced.
      aria-atomic="false"
      aria-relevant="additions"
      // `pointer-events-none` on the region and back on for each toast: the stack is a
      // full-width column in the corner of every screen, and an empty one must not be a
      // transparent sheet over the controls underneath it.
      //
      // Above the overlays, not under them. At `z-40` a failure raised while the judgement
      // drawer was open sat behind a 45% scrim — and a `warn` has no timer, so it waited there
      // invisibly until the drawer closed, by which time the reader had moved on. The drawer
      // is exactly when the mutations that can fail are taken. 70 rather than 60, because a
      // full-screen atlas already claims 60 and a failure report has to outrank a map too.
      className="pointer-events-none fixed inset-x-0 bottom-0 z-[70] flex flex-col items-end gap-2 p-3 sm:inset-x-auto sm:right-0 sm:max-w-[26rem]"
    >
      {toasts.map((toast) => (
        <Notice
          key={toast.id}
          tone={toast.tone}
          title={toast.title}
          className={cn(
            // A raised surface rather than the ground `Notice` wears in the flow: this one is
            // not inside a panel, it is over the page, and the wash was designed to read
            // against a panel behind it.
            "animate-expand pointer-events-auto w-full bg-surface shadow-rim",
            // The edge and the ink still carry the tone. Overriding both halves of `Notice`'s
            // distinction left the two tones identical wherever a toast had no title, which is
            // most of them — so `say()` and `warn()` produced the same object, which is the
            // exact complaint this file was written to answer. A failure is a border and full
            // ink; a receipt is a hairline and the secondary tier. That is the same weight
            // ramp `held` and `cleared` use, applied to the same question, and it spends no
            // hue on chrome that is about to leave.
            toast.tone === "working" ? "border-rule-strong text-ink" : "border-rule text-ink-2",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 wrap-anywhere">{toast.message}</div>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              // Named for its subject. Three stacked toasts meant three buttons called
              // "Dismiss" — one target repeated three times in a voice-control list, and
              // nothing saying which message each one takes away.
              aria-label={`Dismiss: ${toast.title ?? "this message"}`}
              className="-mr-1 -mt-0.5 shrink-0 rounded-sm px-1.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3 transition hover:text-ink"
            >
              Dismiss
            </button>
          </div>
        </Notice>
      ))}
    </div>
  );
}
