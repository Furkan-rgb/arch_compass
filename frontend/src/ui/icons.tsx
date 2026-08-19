import type { SVGProps } from "react";

/**
 * A small hand-drawn icon set.
 *
 * Line icons at a single weight, sized in `em` so they inherit whatever text they sit
 * beside. Every icon is decorative: the label next to it is what a screen reader reads, so
 * they are all `aria-hidden`.
 */
function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      width="1em"
      height="1em"
      {...props}
    >
      {children}
    </svg>
  );
}

export const CompassMark = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="m15.5 8.5-2 5-5 2 2-5z" />
  </Icon>
);

export const PlayIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M8 5.5v13l10-6.5z" />
  </Icon>
);

export const LayersIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="m12 3 8 4.5-8 4.5-8-4.5z" />
    <path d="m4 12.5 8 4.5 8-4.5" />
  </Icon>
);

export const FolderIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.5h7A1.5 1.5 0 0 1 19 10v7.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 3 17.5z" />
  </Icon>
);

export const CaseIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <rect x="4" y="5" width="16" height="15" rx="1.5" />
    <path d="M8 3v4M16 3v4M8 11h8M8 15h5" />
  </Icon>
);

export const BookIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M5 4.5h9a3 3 0 0 1 3 3V20a2.5 2.5 0 0 0-2.5-2.5H5z" />
    <path d="M5 4.5V20" />
  </Icon>
);

export const SlidersIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M5 6h14M5 12h14M5 18h14" />
    <circle cx="9" cy="6" r="2" />
    <circle cx="15" cy="12" r="2" />
    <circle cx="8" cy="18" r="2" />
  </Icon>
);

export const MenuIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Icon>
);

export const SunIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" />
  </Icon>
);

export const MoonIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5" />
  </Icon>
);

export const MonitorIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <rect x="3" y="5" width="18" height="12" rx="1.5" />
    <path d="M9 20h6M12 17v3" />
  </Icon>
);

export const ArrowRight = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M5 12h13M13 7l5 5-5 5" />
  </Icon>
);

export const ChevronDown = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="m6 9 6 6 6-6" />
  </Icon>
);

export const RefreshIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5" />
    <path d="M20 4v4.5h-4.5" />
    <path d="M20 12a8 8 0 0 1-13.7 5.6L4 15.5" />
    <path d="M4 20v-4.5h4.5" />
  </Icon>
);

export const CheckIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </Icon>
);

export const GitBranchIcon = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <circle cx="7" cy="6" r="2.2" />
    <circle cx="7" cy="18" r="2.2" />
    <circle cx="17" cy="9" r="2.2" />
    <path d="M7 8.2v7.6M17 11.2c0 3-3 3.8-6 4.2" />
  </Icon>
);

