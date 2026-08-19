import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../lib/cn";

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
            <h2 className="mt-7 mb-3 font-display text-xl font-semibold tracking-tight text-ink first:mt-0">
              {children}
            </h2>
          ),
          h2: ({ children }) => (
            <h3 className="mt-6 mb-2.5 font-display text-lg font-semibold tracking-tight text-ink first:mt-0">
              {children}
            </h3>
          ),
          h3: ({ children }) => (
            <h4 className="mt-5 mb-2 font-display text-base font-semibold text-ink first:mt-0">
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
            <blockquote className="my-4 border-l-2 border-accent/40 pl-4 text-sm leading-7 text-ink-3">
              {children}
            </blockquote>
          ),
          code: ({ children, className: codeClass }) =>
            codeClass?.startsWith("language-") ? (
              <code className={cn("font-mono text-[12px] leading-6", codeClass)}>{children}</code>
            ) : (
              <code className="rounded-xs border border-rule bg-sunken px-1 py-0.5 font-mono text-[0.86em] text-ink">
                {children}
              </code>
            ),
          pre: ({ children }) => (
            <pre className="scrollbar-slim my-4 overflow-x-auto rounded-md border border-rule bg-sunken/70 p-3.5 text-[12px] leading-6 text-ink">
              {children}
            </pre>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-accent underline decoration-accent/30 underline-offset-4 transition hover:decoration-accent"
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
