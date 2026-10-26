import type { CSSProperties } from "react";

const paths = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  camera: (
    <>
      <rect x="3" y="6" width="13" height="12" rx="2" />
      <path d="m16 10 5-3v10l-5-3" />
    </>
  ),
  book: (
    <>
      <path d="M12 5v16M12 5C8 2 5 3 2 4v15c4-1 7-1 10 2 3-3 6-3 10-2V4c-3-1-6-2-10 1Z" />
    </>
  ),
  arrow: (
    <>
      <path d="M5 12h14m-5-5 5 5-5 5" />
    </>
  ),
  chevron: <path d="m9 5 7 7-7 7" />,
  play: <path d="m8 4 13 8-13 8Z" />,
  stop: <rect x="5" y="5" width="14" height="14" rx="1" />,
  pause: (
    <>
      <path d="M8 5v14M16 5v14" />
    </>
  ),
  reset: (
    <>
      <path d="M3 11a9 9 0 1 1 2.5 7M3 4v7h7" />
    </>
  ),
  video: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="m10 8 6 4-6 4Z" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V3m-5 5 5-5 5 5M3 15v5a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-5" />
    </>
  ),
  refresh: (
    <>
      <path d="M3 11a9 9 0 0 1 16-5l2 3M21 3v6h-6M21 13a9 9 0 0 1-16 5l-2-3M3 21v-6h6" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6m0-10v1" />
    </>
  ),
  shield: (
    <>
      <path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6Z" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" />
      <path d="M12 1v4m11 7h-4m-7 11v-4M1 12h4" />
    </>
  ),
  pulse: <path d="M2 12h5l3-8 4 16 3-8h5" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  chip: (
    <>
      <rect x="5" y="5" width="14" height="14" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3M19 9h3m-3 6h3" />
    </>
  ),
  car: (
    <>
      <path d="m5 8 2-4h10l2 4M4 8h16l1 3v6H3v-6Zm1 9v3m14-3v3M6 12h2m8 0h2" />
    </>
  ),
  truck: (
    <>
      <path d="M2 5h12v12H2Zm12 5h4l4 4v3h-8M16 10v4h6" />
      <circle cx="6" cy="18" r="2" />
      <circle cx="18" cy="18" r="2" />
    </>
  ),
  bus: (
    <>
      <rect x="4" y="3" width="16" height="17" rx="3" />
      <path d="M4 11h16M9 3v8M6 15h2m8 0h2M7 20v2m10-2v2" />
    </>
  ),
  motorcycle: (
    <>
      <circle cx="5" cy="17" r="4" />
      <circle cx="19" cy="17" r="4" />
      <path d="m5 17 5-8 4 8h5L15 5h-3M8 9h5M9 5h2" />
    </>
  ),
  close: <path d="m6 6 12 12M6 18 18 6" />,
} as const;

export type IconName = keyof typeof paths;
export default function Icon({
  name,
  size = 20,
  style,
}: {
  name: IconName;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      {paths[name]}
    </svg>
  );
}
