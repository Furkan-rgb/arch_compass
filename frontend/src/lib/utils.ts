import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/* tailwind-merge groups utilities so that a caller's class can knock out the one baked into
   a component. It only knows Tailwind's own scales, and this design replaced four of them
   with named steps, so it has to be told about those — otherwise `text-meta` is filed under
   *colour*, by the `text-*` fallback, and a component asking for `text-meta text-ink` would
   ship one of the two rather than both. */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        { text: ["micro", "meta", "ui", "body", "read", "sub", "head", "display"] },
      ],
      rounded: [{ rounded: ["control", "panel", "pill"] }],
      shadow: [{ shadow: ["float", "lift"] }],
      leading: [{ leading: ["ui", "reading"] }],
    },
  },
});

/* The class-name helper every vendored shadcn/ui component imports. twMerge is the part
   that earns its place: it lets a caller pass a utility that contradicts one baked into
   the component and have the caller's win, rather than shipping both and leaving the
   cascade to decide by source order. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
