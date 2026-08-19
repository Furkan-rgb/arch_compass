import { cn } from "../lib/cn";
import { PathRef } from "./meta";

/**
 * A pinned source excerpt.
 *
 * Line numbers are rendered beside the code rather than baked into it, so the excerpt can
 * still be selected and copied as the file's own text.
 */
export function SourceExcerpt({
  excerpt,
  startLine,
  className,
}: {
  excerpt: string;
  startLine?: number | null;
  className?: string;
}) {
  const lines = excerpt.replace(/\n$/, "").split("\n");
  return (
    <div
      className={cn(
        "scrollbar-slim overflow-x-auto rounded-md border border-rule bg-sunken/70",
        className,
      )}
    >
      <pre className="min-w-full py-2.5 font-mono text-[12px] leading-[1.65] text-ink">
        <code>
          {lines.map((line, index) => (
            <span key={index} className="grid grid-cols-[3rem_minmax(0,1fr)]">
              <span aria-hidden="true" className="select-none pr-3 text-right text-ink-3/70">
                {startLine ? startLine + index : index + 1}
              </span>
              <span className="whitespace-pre pr-4">{line || " "}</span>
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}

export function EvidenceBlock({
  description,
  path,
  startLine,
  endLine,
  excerpt,
  className,
}: {
  description: string;
  path?: string | null;
  startLine?: number | null;
  endLine?: number | null;
  excerpt?: string | null;
  className?: string;
}) {
  return (
    <div className={cn("rounded-md border border-rule bg-surface", className)}>
      <div className="flex flex-wrap items-start justify-between gap-2 px-3 py-2.5">
        <p className="min-w-0 text-sm leading-6 text-ink">{description}</p>
        {path ? <PathRef path={path} line={startLine} endLine={endLine} /> : null}
      </div>
      {excerpt ? (
        <div className="px-3 pb-3">
          <SourceExcerpt excerpt={excerpt} startLine={startLine} />
        </div>
      ) : null}
    </div>
  );
}
