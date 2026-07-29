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
 * Used by both surfaces that show markdown — a policy's body and an answer in the question
 * dock — because the decisions here are the same for both and are not the kind that should be
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
    <div className="markdown dock__a">
      <Markdown>{text}</Markdown>
    </div>
  );
}
