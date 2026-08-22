import { StrictMode, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { ErrorBoundary } from "./app/error-boundary";
import { ToastProvider, useToast } from "./ui/toast";
import "./styles.css";

/**
 * The workspace is a local process, so a failed request is far more often a moment than a
 * fault: a laptop that slept, a server restarted by the run it is executing, one dropped
 * socket during a poll that has been running for ten minutes.
 *
 * `retry: 1` treated all of those as the answer. Three attempts with a backoff — 1s, 2s, 4s,
 * capped at 8 — covers the whole class without making a genuinely down workspace take
 * appreciably longer to say so, because the first two retries land inside the time it takes
 * a reader to notice anything at all.
 *
 * `staleTime` stays at five seconds as the *default*, which is the right answer for the
 * lists that genuinely move. What can never change — a recorded review, its report, its
 * delta — is immutable by the charter's third commitment and says so per query rather than
 * here, because a global `Infinity` would also freeze the lists.
 */
function makeQueryClient(onMutationError: (error: unknown) => void) {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        retry: 3,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
        refetchOnWindowFocus: false,
      },
    },
    /**
     * The floor under every mutation: a failure that nothing else reports is reported here.
     *
     * A mutation that renders its own error in place — the decision bar, a policy form —
     * still gets a toast, deliberately. The complaint the toast answers is not that failures
     * are unreported but that they are reported *where you are not looking*, and a decision
     * taken from the keyboard while scrolled away is exactly that case.
     *
     * A call site that genuinely owns its failure, and would be saying the same thing twice
     * in the same eyeline, opts out with `meta: { handled: true }`.
     */
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.handled) return;
        onMutationError(error);
      },
    }),
  });
}

/**
 * The client is built here rather than at module scope because it needs the toast, and the
 * toast is React context. `useState` with an initialiser rather than `useMemo`: this must be
 * created exactly once for the life of the application, and `useMemo` is a performance hint
 * that React is allowed to discard.
 */
function Queries({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [client] = useState(() =>
    makeQueryClient((error) =>
      toast.warn(error instanceof Error ? error.message : String(error), "That did not go through"),
    ),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <Queries>
        <BrowserRouter>
          {/* The last resort. The one inside the shell's `<main>` keeps the rail alive for
              anything a route threw; this one is for an error thrown by the shell itself. */}
          <ErrorBoundary>
            <App />
          </ErrorBoundary>
        </BrowserRouter>
      </Queries>
    </ToastProvider>
  </StrictMode>,
);
