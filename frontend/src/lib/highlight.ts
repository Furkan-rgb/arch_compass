import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";

/**
 * Colouring code, without shipping somebody else's colours.
 *
 * The highlighter is used as a tokeniser only: it emits `hljs-…` class names and the palette
 * lives in `styles.css` alongside every other colour, so a keyword follows the workspace's
 * theme rather than a bundled light and dark stylesheet that would have to be kept in step
 * with it. That is also why no highlight.js CSS is imported anywhere.
 *
 * Languages are registered one by one rather than taken from the full build, which is about
 * 900KB of grammars for a repository the analyser only reads Python from. These are what a
 * policy body, a report or an excerpt actually contains.
 */
const LANGUAGES: Record<string, Parameters<typeof hljs.registerLanguage>[1]> = {
  python,
  json,
  bash,
  yaml,
  sql,
  markdown,
  typescript,
  javascript,
  xml,
};

for (const [name, definition] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, definition);
}

hljs.registerAliases(["py"], { languageName: "python" });
hljs.registerAliases(["sh", "shell", "console", "zsh"], { languageName: "bash" });
hljs.registerAliases(["yml"], { languageName: "yaml" });
hljs.registerAliases(["ts", "tsx"], { languageName: "typescript" });
hljs.registerAliases(["js", "jsx"], { languageName: "javascript" });
hljs.registerAliases(["md"], { languageName: "markdown" });
hljs.registerAliases(["html"], { languageName: "xml" });

export const SUPPORTED_LANGUAGES = Object.keys(LANGUAGES);

/** Whether a fence's language is one we can actually colour. */
export function isSupported(language: string | undefined): boolean {
  return Boolean(language && hljs.getLanguage(language));
}

/**
 * Code as HTML with `hljs-…` spans, or as escaped text when the language is unknown.
 *
 * Never guesses. Automatic detection on a four-line excerpt is a coin toss that produces
 * confidently wrong colouring — a Python docstring read as a shell heredoc — and code shown
 * in the wrong colours is worse than code shown in none, because the colours are a claim
 * about what the tokens mean.
 */
export function highlight(code: string, language?: string): string {
  if (!isSupported(language)) return escapeHtml(code);
  try {
    return hljs.highlight(code, { language: language as string, ignoreIllegals: true }).value;
  } catch {
    // A grammar that throws on a partial excerpt is not a reason to lose the excerpt.
    return escapeHtml(code);
  }
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * The language an excerpt is written in, inferred from the file it was read out of.
 *
 * The path is evidence and a guess is not: a `.py` file is Python, and a file this list does
 * not name is left uncoloured rather than approximated.
 */
const BY_EXTENSION: Record<string, string> = {
  py: "python",
  pyi: "python",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  sql: "sql",
  md: "markdown",
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  sh: "bash",
  bash: "bash",
  html: "xml",
  xml: "xml",
  toml: "ini",
};

export function languageForPath(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  const extension = path.split(".").pop()?.toLowerCase();
  const language = extension ? BY_EXTENSION[extension] : undefined;
  return isSupported(language) ? language : undefined;
}
