/**
 * The pair of controls in the page header: export the review as a file, and open the panel
 * that asks about it. Together because they are one row of buttons and each is a few lines;
 * apart from the header because the rule about when asking is allowed lives here.
 */

import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { AiChatIcon } from "../../ai-icon";
import { ask } from "../../review-capabilities";
import type { ReviewStatus } from "../../types";

/**
 * The way into the question panel, and the one place the `ask` rule is enforced.
 *
 * Blocked states keep the button on screen rather than dropping it. A reader who never sees
 * the affordance never learns the review can be asked about at all, and this page is where
 * they would learn it — so it stays, greyed, with the reason on it.
 */
export function AskAction({
  status,
  expanded,
  onToggle,
}: {
  status: ReviewStatus | undefined;
  expanded: boolean;
  onToggle: () => void;
}) {
  const refusal = ask(status);
  const button = (
    <Button
      type="button"
      variant="primary"
      aria-expanded={refusal ? undefined : expanded}
      disabled={refusal !== null}
      onClick={refusal ? undefined : onToggle}
    >
      <AiChatIcon size={14} /> Ask about this review
    </Button>
  );
  if (!refusal) return button;
  return (
    <Tooltip>
      {/* The span is load-bearing: a disabled button dispatches no pointer events, so the
          trigger has to be something above it that does. It takes the tab stop the button
          gave up, so the reason reaches a reader arriving by keyboard too. */}
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            "inline-flex rounded-control",
            // The ring the button can no longer draw for itself, on the element that now
            // holds its tab stop. Same 2px of accent every focusable thing here draws.
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
          )}
        >
          {button}
        </span>
      </TooltipTrigger>
      <TooltipContent>{refusal}</TooltipContent>
    </Tooltip>
  );
}

/**
 * The review as the file it was already written as.
 *
 * An anchor rather than a request: the workspace answers with `Content-Disposition`, so the
 * browser saves the response itself. Nothing is fetched, held or revoked here, and the
 * control is keyboard-reachable because it is a link — which is also why this is the one
 * call that does not go through `api.ts`, where every function reads a body.
 *
 * `download` is on it so a refusal stays a failed download rather than navigating the reader
 * off their own review onto a page of JSON.
 *
 * Absent rather than greyed while there is nothing to hand over, which is the opposite of
 * what asking does — and for the opposite reason. Asking is a capability of the review that
 * a reader has to learn exists; exporting a report that does not exist is not a refusal
 * worth explaining, it is a run that has not finished.
 */
export function ExportAction({ reviewId, available }: { reviewId: string; available: boolean }) {
  if (!available) return null;
  return (
    <Button asChild>
      <a href={`/api/reviews/${encodeURIComponent(reviewId)}/report`} download>
        <Download size={14} aria-hidden /> Export Markdown
      </a>
    </Button>
  );
}
