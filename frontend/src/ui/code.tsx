import { cn } from "../lib/cn";
import { highlight, languageForPath } from "../lib/highlight";
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
  path,
  language,
  className,
}: {
  excerpt: string;
  startLine?: number | null;
  /** The file it was read from; the extension is what decides the colouring. */
  path?: string | null;
  /** Overrides the path, for code that arrived without one — a Markdown fence. */
  language?: string;
  className?: string;
}) {
  const body = excerpt.replace(/\n$/, "");
  const lines = body.split("\n");
  const resolved = language ?? languageForPath(path);
  // The whole excerpt is highlighted once and the numbers are a separate column, because
  // highlighting line by line would end a docstring at every newline and start a new one.
  // The two columns line up because they share a line height and neither of them wraps.
  const coloured = highlight(body, resolved);

  return (
    <div
      className={cn(
        "scrollbar-slim overflow-x-auto rounded-md border border-rule bg-sunken/70",
        className,
      )}
    >
      <div className="flex min-w-full py-2.5 font-mono text-[12px] leading-[1.65]">
        <div
          aria-hidden="true"
          className="shrink-0 select-none px-3 text-right tabular-nums text-ink-3/70"
        >
          {lines.map((_, index) => (
            <div key={index}>{startLine ? startLine + index : index + 1}</div>
          ))}
        </div>
        {/* The excerpt is the file's own text, so it stays selectable and copyable without
            the numbers coming with it. */}
        <pre className="min-w-0 flex-1 pr-4 text-ink">
          <code
            className={resolved ? `language-${resolved}` : undefined}
            dangerouslySetInnerHTML={{ __html: coloured || " " }}
          />
        </pre>
      </div>
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
          <SourceExcerpt excerpt={excerpt} startLine={startLine} path={path} />
        </div>
      ) : null}
    </div>
  );
}
