import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../lib/cn";
import { highlight, isSupported } from "../lib/highlight";

/**
 * A heading may be a name.
 *
 * The report leads every finding with its identifier in backticks, because scanning beats
 * reading and a heading is what the eye lands on. Inline code elsewhere is a chip — a border
 * and a fill, so a symbol inside a sentence is visibly not part of it — and a chip is the
 * wrong shape for a heading, which reads as a tag rather than as a title. Inside a heading
 * the code keeps the mono face, which is the part that carries meaning, and drops the box.
 */
const NAMED_HEADING =
  "wrap-anywhere [&>code]:border-0 [&>code]:bg-transparent [&>code]:px-0 [&>code]:py-0 [&>code]:text-[0.92em]";

/** Everything after `language-` on a fence, which is all the fence tells us. */
function fenceLanguage(className: string | undefined): string | undefined {
  const found = /language-([\w+-]+)/.exec(className ?? "");
  return found?.[1]?.toLowerCase();
}

/**
 * Policy bodies and rendered reports.
 *
 * Every element is given a class here rather than inheriting one from a wrapper, because a
 * policy body is authored Markdown and has to read as a document — headings that are
 * actually headings, tables that scroll rather than overflow, code that stays monospace.
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("max-w-none", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h2
              className={cn(
                "mt-7 mb-3 font-display text-xl font-semibold tracking-tight text-ink first:mt-0",
                NAMED_HEADING,
              )}
            >
              {children}
            </h2>
          ),
          h2: ({ children }) => (
            <h3
              className={cn(
                "mt-6 mb-2.5 font-display text-lg font-semibold tracking-tight text-ink first:mt-0",
                NAMED_HEADING,
              )}
            >
              {children}
            </h3>
          ),
          h3: ({ children }) => (
            <h4
              className={cn(
                "mt-5 mb-2 font-display text-base font-semibold text-ink first:mt-0",
                NAMED_HEADING,
              )}
            >
              {children}
            </h4>
          ),
          h4: ({ children }) => (
            <h5 className="mt-4 mb-1.5 text-sm font-semibold uppercase tracking-[0.08em] text-ink-3 first:mt-0">
              {children}
            </h5>
          ),
          p: ({ children }) => (
            <p className="my-3 text-sm leading-7 text-ink-2 first:mt-0 last:mb-0">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="my-3 list-disc space-y-1.5 pl-5 text-sm leading-7 text-ink-2 marker:text-ink-3">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-3 list-decimal space-y-1.5 pl-5 text-sm leading-7 text-ink-2 marker:text-ink-3">
              {children}
            </ol>
          ),
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote className="my-4 border-l-2 border-rule-strong pl-4 text-sm leading-7 text-ink-3">
              {children}
            </blockquote>
          ),
          code: ({ children, className: codeClass }) => {
            const language = fenceLanguage(codeClass);
            if (!codeClass?.startsWith("language-")) {
              return (
                <code className="rounded-xs border border-rule bg-sunken px-1 py-0.5 font-mono text-[0.86em] text-ink wrap-anywhere">
                  {children}
                </code>
              );
            }
            // A fence that names a language we hold a grammar for is coloured; one that
            // names something else, or nothing, is left as plain monospace rather than
            // guessed at. Colour here is a claim about what a token means.
            const text = String(children).replace(/\n$/, "");
            if (!isSupported(language)) {
              return (
                <code className={cn("font-mono text-[12px] leading-6", codeClass)}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn("font-mono text-[12px] leading-6", codeClass)}
                dangerouslySetInnerHTML={{ __html: highlight(text, language) }}
              />
            );
          },
          pre: ({ children }) => (
            <pre className="scrollbar-slim my-4 overflow-x-auto rounded-md border border-rule bg-sunken/70 p-3.5 text-[12px] leading-6 text-ink">
              {children}
            </pre>
          ),
          // `text-mark` is ink now, and the paragraph around it is `text-ink-2`, so what
          // used to be a hue is half a step of lightness against its own sentence. The
          // weight is what replaces it — the underline was always here and was never
          // carrying this on its own. It rests at half strength and goes to full ink on
          // hover, so the link still answers the pointer.
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-mark underline decoration-mark/50 underline-offset-4 transition hover:decoration-mark"
            >
              {children}
            </a>
          ),
          hr: () => <hr className="my-6 border-0 border-t border-rule" />,
          table: ({ children }) => (
            <div className="scrollbar-slim my-4 overflow-x-auto rounded-md border border-rule">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-sunken/70">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-rule px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-rule px-3 py-2 align-top leading-6 text-ink-2">
              {children}
            </td>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
