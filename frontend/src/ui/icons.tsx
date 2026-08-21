import {
  ArrowLeft as LucideArrowLeft,
  ArrowRight as LucideArrowRight,
  ArrowUp as LucideArrowUp,
  BookOpen,
  Check,
  ChevronDown as LucideChevronDown,
  ClipboardList,
  Compass,
  Folder,
  GitBranch,
  Layers,
  Menu,
  Monitor,
  Moon,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sun,
  type LucideIcon,
} from "lucide-react";
import type { SVGProps } from "react";

/**
 * The interface's icons, named for what they mean here rather than for what they draw.
 *
 * These were hand-drawn — a `24` box, stroke 1.6, round caps — which is exactly what Lucide
 * is, maintained by more people and drawn on one grid. The hand-drawn set was competing with
 * it on optical consistency and losing, so this is now a naming layer and nothing more.
 *
 * The names are kept because they are the ones this product uses: a `CaseIcon` is a review
 * case, and a call site should not have to know that a case happens to be drawn as a
 * clipboard. Renaming the icon underneath is then a one-line change here rather than a sweep.
 *
 * Sized in `em` so an icon is a fixed fraction of whatever text it sits beside, and every one
 * is `aria-hidden`: each sits next to its own label, and announcing both says it twice.
 * `ui/mark.tsx` is the other half of this — the marks a *descriptor* wears, which are chosen
 * from a fixed vocabulary rather than picked per call site.
 */
function icon(Source: LucideIcon) {
  return function Wrapped(props: SVGProps<SVGSVGElement>) {
    return (
      <Source
        aria-hidden="true"
        focusable="false"
        strokeWidth={1.75}
        width="1em"
        height="1em"
        {...props}
      />
    );
  };
}

export const CompassMark = icon(Compass);
export const PlayIcon = icon(Play);
export const LayersIcon = icon(Layers);
export const FolderIcon = icon(Folder);
export const CaseIcon = icon(ClipboardList);
export const BookIcon = icon(BookOpen);
export const SlidersIcon = icon(SlidersHorizontal);
export const MenuIcon = icon(Menu);
export const SunIcon = icon(Sun);
export const MoonIcon = icon(Moon);
export const MonitorIcon = icon(Monitor);
export const ArrowRight = icon(LucideArrowRight);
export const ArrowLeft = icon(LucideArrowLeft);
export const ChevronDown = icon(LucideChevronDown);
export const RefreshIcon = icon(RefreshCw);
export const CheckIcon = icon(Check);
export const GitBranchIcon = icon(GitBranch);
export const SearchIcon = icon(Search);
export const ArrowUp = icon(LucideArrowUp);

/**
 * A decision the branch still holds, against a verdict that has since moved.
 *
 * Named for the thing rather than the drawing, like the rest of this file: the row it sits on
 * says "decided against held, now material", and what the mark adds is that this has been
 * round once before. Not a mark from `ui/mark.tsx` — a drifted decision is a relationship
 * between a decision and a verdict rather than a value either of them carries, so it has no
 * place in that vocabulary.
 */
export const DriftedIcon = icon(RotateCcw);

/**
 * The GitHub mark, still drawn by hand.
 *
 * Lucide dropped brand icons, and a brand mark is the one thing that genuinely cannot be
 * substituted: an approximation of somebody's logo is worse than no logo. Filled rather than
 * stroked, because that is what the mark is.
 */
export const GithubIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" className="size-4" {...props}>
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
  </svg>
);
