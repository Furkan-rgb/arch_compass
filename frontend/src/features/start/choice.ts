/**
 * The repository chosen on `/start`, kept alive across the unmount that a navigation is.
 *
 * `/start` is a route element, so leaving it — to `/settings` to choose a model, to
 * `/policies` to read what will be applied, anywhere — unmounts the page and `useState`
 * throws the choice away. A repository found by browsing the filesystem, or cloned from an
 * address, or ten minutes of ticked folders, all gone. And the page itself is what sends
 * people away: under its own run button it prints "Both are needed before a review can run"
 * with a link straight to Settings.
 *
 * Module state rather than storage of any kind, because the lifetime wanted here is exactly
 * the lifetime of the loaded page: it survives every in-app navigation and dies with a
 * reload. `sessionStorage` would survive reloads for the whole tab, and `?root=` survives
 * them too while putting an absolute path from one machine into a link that looks shareable
 * — and would have to be rewritten on every keystroke into the debounced path field. Both do
 * more than was asked for, in the one direction that was ruled out.
 *
 * Deliberately not `localStorage`, where `lib/theme.ts`, `lib/editor.ts` and
 * `features/atlas/pulse.ts` keep theirs: those remember preferences, which are meant to
 * outlive the visit. This is a half-filled form, and a half-filled form that comes back a
 * week later is a surprise rather than a courtesy.
 */
export type StartChoice = {
  root: string;
  excluded: string[];
  /** Whether to start from an empty case rather than the one this repository already has. */
  clean: boolean;
};

const NOTHING: StartChoice = { root: "", excluded: [], clean: false };

let remembered: StartChoice = NOTHING;

export const rememberedChoice = (): StartChoice => remembered;

export const rememberChoice = (choice: StartChoice): void => {
  remembered = choice;
};

/**
 * Module state outlives a `render`, so without this one test choosing a repository would
 * hand it to every test after it in the file. `start-page.test.tsx` clears it in `beforeEach`.
 */
export const forgetChoice = (): void => {
  remembered = NOTHING;
};
