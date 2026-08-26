import { Component, type ErrorInfo, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { Button } from "../ui/button";

/**
 * What a render error looks like, instead of a blank page.
 *
 * There was no boundary anywhere: no `componentDidCatch`, no router `errorElement`. React
 * unmounts the whole tree on an uncaught render error, so a reviewer part way down a docket
 * got a white canvas that kept the URL — the open row, the filter and any half-typed waiver
 * reason gone, and nothing on screen saying what had happened or that reloading would help.
 *
 * It is mounted at two levels and they answer different questions. Inside the shell's
 * `<main>` the rail survives, so the reader can navigate away from the one page that broke
 * without losing the application. Around `<App/>` it is the last resort, for an error thrown
 * by the shell itself, where a reload is the only move left.
 */
function Fallback({ error, onReset }: { error: Error; onReset: () => void }) {
  return (
    // Its own box, because the two levels land in different places: inside the shell a
    // workspace route hands its child the bare viewport, and outside the shell there is no
    // measured column at all.
    <div role="alert" className="mx-auto w-full max-w-[46rem] p-4 sm:p-6">
      <div className="rounded-lg border border-rule-strong bg-surface p-6 shadow-rim">
        <h1 className="font-display text-lg font-semibold tracking-tight text-ink">
          This screen stopped part way through
        </h1>
        <p className="mt-2 max-w-[62ch] text-sm leading-6 text-ink-2">
          Nothing recorded is lost — a review is a record on the workspace, not something this
          page was holding. Anything typed here and not yet saved is.
        </p>
        {/* The message verbatim, the way `problem()` surfaces a server's own words: a reader
            about to report this needs the sentence, not a paraphrase of it. `wrap-anywhere`
            because it is regularly a URL or an absolute path with no break opportunity. */}
        <p className="mt-4 rounded-md border border-rule bg-sunken px-3.5 py-3 font-mono text-[12px] leading-5 text-ink-2 wrap-anywhere">
          {error.message || String(error)}
        </p>
        {/* The cheapest move first, and it is the one the component already knew how to make.
            `onReset` was wired only to the onClick of a link that navigates away, so the two
            things on offer were "throw the whole application away and reload" and "leave this
            screen" — and a render error is very often transient: a poll that landed mid-render,
            a fixture that arrived half-written. Re-rendering the same route costs nothing.

            It is a promise about the attempt rather than about the outcome. A deterministic
            error throws again on the first paint after the reset and the fallback comes
            straight back, which looks like a dead button unless it is written down. */}
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <Button onClick={onReset}>Try this screen again</Button>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Reload the page
          </Button>
          <Link
            to="/reviews"
            onClick={onReset}
            className="inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-semibold text-ink-2 underline decoration-rule-strong underline-offset-2 transition hover:text-ink"
          >
            Go to your reviews
          </Link>
        </div>
      </div>
    </div>
  );
}

type Props = { children: ReactNode; resetKey?: string };

/**
 * `getDerivedStateFromError` rather than `componentDidCatch` alone: the first is what turns
 * the thrown error into the state that renders the fallback, and it runs in the render pass
 * so nothing paints between the throw and the message.
 *
 * `resetKey` is the route. A boundary that latches for ever turns one broken page into a
 * broken application — the reader navigates away, the URL changes, and the fallback is still
 * there because nothing told it the subject had changed.
 */
class Boundary extends Component<Props, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  componentDidUpdate(previous: Props) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // The console is the only recorder this frontend has. It is worth the line: the fallback
    // shows the message, and the component stack is what says which surface threw.
    console.error("ArchCompass render error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return <Fallback error={this.state.error} onReset={() => this.setState({ error: null })} />;
    }
    return this.props.children;
  }
}

/**
 * The boundary as a function component, so the route can be read with a hook.
 *
 * Both mounts sit inside the router — the outer one wraps `<App/>` rather than the
 * `BrowserRouter` above it — so both can reset on the path, and the fallback's own link to
 * the reviews has the context it needs to be a link at all.
 */
export function ErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <Boundary resetKey={pathname}>{children}</Boundary>;
}
