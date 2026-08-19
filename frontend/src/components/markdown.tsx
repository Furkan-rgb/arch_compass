import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => (
          <h1 className="mt-6 mb-3 font-display text-2xl font-semibold tracking-tight text-ink first:mt-0">
            {children}
          </h1>
        ),

        h2: ({ children }) => (
          <h2 className="mt-6 mb-3 font-display text-xl font-semibold tracking-tight text-ink first:mt-0">
            {children}
          </h2>
        ),

        h3: ({ children }) => (
          <h3 className="mt-5 mb-2 font-display text-base font-semibold text-ink first:mt-0">{children}</h3>
        ),

        p: ({ children }) => <p className="my-3 text-sm leading-7 text-ink-2 first:mt-0 last:mb-0">{children}</p>,

        ul: ({ children }) => (
          <ul className="my-3 list-disc space-y-1.5 pl-6 text-sm leading-7 text-ink-2">{children}</ul>
        ),

        ol: ({ children }) => (
          <ol className="my-3 list-decimal space-y-1.5 pl-6 text-sm leading-7 text-ink-2">{children}</ol>
        ),

        li: ({ children }) => <li>{children}</li>,

        strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,

        em: ({ children }) => <em className="italic">{children}</em>,

        blockquote: ({ children }) => (
          <blockquote className="my-4 border-l-2 border-primary/30 pl-4 text-sm italic text-ink-3">
            {children}
          </blockquote>
        ),

        code: ({ children }) => (
          <code className="rounded-md bg-canvas-strong px-1.5 py-0.5 font-mono text-[0.875em] text-ink">
            {children}
          </code>
        ),

        pre: ({ children }) => (
          <pre className="my-4 overflow-x-auto rounded-xl bg-canvas-strong p-4 text-sm leading-6 text-ink">
            {children}
          </pre>
        ),

        a: ({ children, href }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-primary underline decoration-primary/30 underline-offset-4 hover:decoration-primary"
          >
            {children}
          </a>
        ),

        hr: () => <hr className="my-6 border-rule" />,

        table: ({ children }) => (
          <div className="my-4 overflow-x-auto">
            <table className="w-full border-collapse text-sm">{children}</table>
          </div>
        ),

        th: ({ children }) => (
          <th className="border-b border-rule px-3 py-2 text-left font-semibold text-ink">{children}</th>
        ),

        td: ({ children }) => <td className="border-b border-rule px-3 py-2 align-top text-ink-2">{children}</td>,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
