/**
 * The guards a shortcut bound at the document has to carry.
 *
 * Three surfaces bind keys this way — the decision bar's `A`/`P`/`W`, the docket's `j`/`k`,
 * and the shell's `⌘K` and `?` — and each of them wrote its own version of the same two
 * questions. The palette's version was a doc comment describing guards the handler did not
 * have: `Ctrl+K` inside a waiver's reason box, which on macOS is kill-to-end-of-line, opened
 * the palette instead of editing the line.
 *
 * So the questions live here once. What they are *not* is a keybinding registry: which key
 * does what stays at the surface that owns the key, because that is the part a reader of
 * that file needs to see.
 */

/**
 * Whether the keystroke belongs to something being typed into.
 *
 * With single letters bound at the document there is no keystroke in a text field that is
 * not also a shortcut — a reviewer typing the word "Park" into a waiver's reason means the
 * word — so this guard is what makes those shortcuts safe to have at all.
 *
 * `isContentEditable` as well as the three tag names: the Markdown fields are plain
 * textareas today, and an editable div is the shape this misses first.
 */
export function isTyping(target: EventTarget | null): boolean {
  const node = target as HTMLElement | null;
  return Boolean(
    node && (node.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(node.tagName)),
  );
}

/**
 * Whether something modal is already up.
 *
 * A modal owns the keyboard while it is open: it has a focus trap, and its own Escape
 * handler. A second shortcut firing underneath it either opens a dialog over a dialog — two
 * Escape handlers, both listening at the document, fighting over one keystroke — or acts on
 * a surface the reader cannot see. Asked of the DOM rather than of a store, because
 * `aria-modal` is the thing that is already true of every one of them.
 */
export function hasOpenModal(): boolean {
  return Boolean(document.querySelector('[aria-modal="true"]'));
}

/**
 * Whether something with unsaved input is open inside the page.
 *
 * The same layering rule as `hasOpenModal`, one level down. A reveal is not modal — it has no
 * focus trap and the page around it stays live — but it does own Escape while it is open,
 * because Escape is how it is cancelled and because what it holds is a sentence somebody is
 * part-way through typing. Without this the docket's Escape, bound at the document, closed the
 * whole row from one Tab past the textarea and took the half-written waiver with it, which is
 * `docs/experience.md`'s "never navigate away from unsaved input" broken by a keystroke the
 * shortcut sheet advertises as "close what is open".
 *
 * A data attribute rather than the panel's id: the id is generated per bar and what this asks
 * is a property of the kind of thing, not of one instance of it.
 */
export function hasOpenReveal(): boolean {
  return Boolean(document.querySelector("[data-reveal]"));
}

/**
 * A plain keystroke: no browser command underneath it, nothing being typed into, no modal
 * already holding the keyboard.
 *
 * Shift is not a modifier for this purpose. `?` is Shift and `/` on most layouts, so
 * refusing it would refuse the shortcut this guard exists to protect.
 */
export function isPlainShortcut(event: KeyboardEvent): boolean {
  if (event.metaKey || event.ctrlKey || event.altKey) return false;
  return !isTyping(event.target) && !hasOpenModal();
}
