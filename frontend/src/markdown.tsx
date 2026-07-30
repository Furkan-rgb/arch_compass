import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypePrismGenerator from "rehype-prism-plus/generator";
import bash from "refractor/bash";
import { refractor } from "refractor/core";
import diff from "refractor/diff";
import json from "refractor/json";
import python from "refractor/python";
import sql from "refractor/sql";
import typescript from "refractor/typescript";
import yaml from "refractor/yaml";
import remarkGfm from "remark-gfm";

/**
 * The languages worth carrying, rather than the two hundred a default build would.
 *
 * Every one is something this workspace actually shows: the repositories under review are
 * Python, cases and model configuration are YAML, the API speaks JSON, commands are shell,
 * this frontend is TypeScript, and an answer proposing a change often writes it as a diff.
 * Anything else falls back to plain monospace, which is the honest result — a block coloured
 * by a grammar that does not fit reads as wrong rather than as unstyled.
 *
 * Registered against refractor's bare core rather than taken from a ready-made bundle, and
 * the measured cost in the committed bundle is why. Against no highlighting at all this route
 * adds 16KB gzipped; highlight.js, the other obvious choice and the first one tried, adds 54.
 * Nearly all of that difference is engine rather than grammars — trimming its language list
 * changed the total by two hundred bytes — so the choice is the engine, not the list.
 */
for (const language of [bash, diff, json, python, sql, typescript, yaml]) {
  refractor.register(language);
}

//: `ignoreMissing` so a fence naming something outside that list renders as plain code rather
//: than throwing. An answer naming an unregistered language is a formatting question, and it
//: must not be able to take down the page that is reporting it.
const rehypePrism = rehypePrismGenerator(refractor);

/**
 * Markdown as this workspace renders it, in one place.
 *
 * Used by both surfaces that show markdown — a policy's body and an answer in the ask
 * panel — because the decisions here are the same for both and are not the kind that should be
 * made twice: which plugins run, which languages are coloured, and what happens to HTML.
 *
 * Raw HTML is escaped rather than rendered. `rehype-raw` is deliberately not installed, so
 * neither a policy file on disk nor a sentence a model wrote can become markup on the page.
 *
 * A block is coloured only when it says which language it is. There is no detection here and
 * that is deliberate: a short snippet is ambiguous between half these grammars, and a wrong
 * guess colours the wrong words with complete confidence.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[[rehypePrism, { ignoreMissing: true }]]}
    >
      {children}
    </ReactMarkdown>
  );
}

/**
 * An answer as the model wrote it: prose, with code shown as code.
 *
 * The same renderer the Policies page uses, so a fenced block, a table or a bulleted list
 * reads the same wherever it appears. It also matters more here than there — an answer about
 * a boundary routinely shows the two-line change it is describing, and a diff rendered as one
 * run-on paragraph is worse than no example at all.
 *
 * Safe to call on a partial answer. An unclosed fence is treated as a code block running to
 * the end of what has arrived, which is exactly right for a block still being written; it is
 * highlighted from the first line rather than turning colour once the answer finishes.
 *
 * Lives here rather than beside the review page because two surfaces render model prose now
 * — the review conversation and the per-question discussion — and the second importing it
 * from the first would make the page and a component it renders import each other.
 */
export function AnswerProse({ text }: { text: string }) {
  return (
    <div className="markdown answer-prose">
      <Markdown>{text}</Markdown>
    </div>
  );
}

/**
 * Which grammar a file's own extension names, for code the application read from disk.
 *
 * The no-detection rule above is about a fenced block, where all anyone has is the characters
 * and a short snippet is ambiguous between half these grammars. A recorded excerpt is a
 * different situation with a different amount of evidence: it was read out of a file at a path
 * the review pinned, and `.py` is not a guess about that file — it is what the repository calls
 * it. So this is the same policy applied to better information, not an exception to it.
 *
 * Exactly the grammars registered above, and nothing more. A path this does not recognise gets
 * `null` and renders as plain monospace, which stays the honest answer: colouring a `.rb` file
 * with the Python grammar would light up the wrong words with complete confidence, and a
 * repository ArchCompass cannot yet analyse is one whose excerpts it should not pretend to
 * understand either.
 */
const EXCERPT_LANGUAGES: Record<string, string> = {
  py: "python",
  ts: "typescript",
  tsx: "typescript",
  js: "typescript",
  jsx: "typescript",
  mjs: "typescript",
  cjs: "typescript",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  sh: "bash",
  bash: "bash",
  sql: "sql",
  diff: "diff",
  patch: "diff",
};

/** The grammar for a recorded excerpt's path, or `null` where there is not one to be sure of. */
export function languageForPath(path: string | null | undefined): string | null {
  if (!path) return null;
  // The last dot in the last segment, so `a.b/c` has no extension and `mod.test.ts` is
  // TypeScript. A dotfile with no extension — `.gitignore` — has nothing before the dot and is
  // deliberately not matched: its name is not a claim about a grammar.
  const name = path.split(/[/\\]/).pop() ?? "";
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return null;
  return EXCERPT_LANGUAGES[name.slice(dot + 1).toLowerCase()] ?? null;
}

/**
 * As much of a hast node as this renderer reads, declared here rather than imported.
 *
 * `import type { ElementContent } from "hast"` is the obvious spelling and is a trap in this
 * checkout: `@types/hast` is not hoisted into the project, so that specifier resolved to a copy
 * outside it entirely and every field then mismatched refractor's own copy structurally. A
 * three-field shape is both immune to that and a more honest statement of the coupling — the
 * only thing this depends on is that refractor emits text and elements.
 *
 * Every field optional so the real node types are assignable to it: a text node has no
 * children, a doctype has neither, and none of them has to be enumerated here to be handled.
 */
interface TokenNode {
  type: string;
  value?: string | undefined;
  properties?: { className?: unknown } | null | undefined;
  children?: TokenNode[] | undefined;
}

/** A hast node's class list as React wants it, whatever shape the property arrived in. */
function classNameOf(value: unknown): string | undefined {
  if (Array.isArray(value)) return value.join(" ") || undefined;
  return typeof value === "string" ? value || undefined : undefined;
}

/**
 * Refractor's tree as React nodes, which is the whole of what this renderer has to do.
 *
 * `rehype-prism-plus` does this for markdown by running inside a rehype pipeline that
 * `react-markdown` already owns. There is no pipeline here — the excerpt is a string and a
 * path, not a document — so the alternative to twenty lines of recursion is a second markdown
 * renderer wrapped around code fenced by us, which would mean composing markdown to get its
 * parser to take it apart again.
 *
 * Text and elements are the only node types refractor emits. Anything else is dropped rather
 * than stringified: this renders the reader's own file, and a node this does not understand is
 * better absent than guessed at.
 */
function tokensToReact(nodes: TokenNode[]): ReactNode[] {
  return nodes.map((node, index) => {
    if (node.type === "text") return node.value ?? "";
    if (node.type !== "element") return null;
    return (
      <span key={index} className={classNameOf(node.properties?.className)}>
        {tokensToReact(node.children ?? [])}
      </span>
    );
  });
}

/**
 * One excerpt's code, coloured where its path says which grammar to use.
 *
 * The excerpts every grounded answer carries were the last code in the product still rendered
 * as undifferentiated monospace, which mattered most where they matter most: the reader is
 * being shown four copies of a constant, or the one implementation behind a port, and is
 * expected to notice something about them.
 *
 * Falls back to the string itself rather than to an error. A grammar can throw on input it did
 * not expect — an excerpt is a fragment of a file, so a span can begin inside a construct that
 * never closes — and losing the reader's own code to a highlighter is a far worse outcome than
 * showing it plain.
 */
export function HighlightedCode({
  code,
  language,
}: {
  code: string;
  language: string | null;
}) {
  if (!language || !refractor.registered(language)) return <>{code}</>;
  try {
    return <>{tokensToReact(refractor.highlight(code, language).children)}</>;
  } catch {
    return <>{code}</>;
  }
}
