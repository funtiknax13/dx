import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>
const base = (p: P) => ({
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  ...p,
})

export const IconRunner = (p: P) => (
  <svg {...base(p)}>
    <circle cx="15.5" cy="4.5" r="1.7" />
    <path d="M14 6.5L10.5 13L7.5 16L9 20" />
    <path d="M10.5 13L14 14.5L12.5 20" />
    <path d="M13.3 7.2L16.5 6.5L18.5 9M13.3 7.2L10.8 9.5L12 12.5" />
  </svg>
)
export const IconPin = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z" />
    <circle cx="12" cy="10" r="2.5" />
  </svg>
)
export const IconClock = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
)
export const IconCalendar = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M3 9h18M8 3v4M16 3v4" />
  </svg>
)
export const IconRoute = (p: P) => (
  <svg {...base(p)}>
    <circle cx="6" cy="19" r="2" />
    <circle cx="18" cy="5" r="2" />
    <path d="M8 19h6a3 3 0 003-3V9M16 5H9a3 3 0 00-3 3v8" />
  </svg>
)
export const IconDownload = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
  </svg>
)
export const IconTrophy = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 4h8v4a4 4 0 01-8 0V4z" />
    <path d="M8 5H5v2a3 3 0 003 3M16 5h3v2a3 3 0 01-3 3M10 14h4l1 6H9l1-6z" />
  </svg>
)
export const IconArrow = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
)
export const IconCheck = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 12l5 5L20 6" />
  </svg>
)
export const IconX = (p: P) => (
  <svg {...base(p)}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)
export const IconMenu = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
)
export const IconMail = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="M4 7l8 6 8-6" />
  </svg>
)
export const IconUser = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 20c0-4 4-6 8-6s8 2 8 6" />
  </svg>
)
export const IconFlag = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 21V4M5 4h11l-2 4 2 4H5" />
  </svg>
)
export const IconMountain = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 20l6-11 4 6 2-3 6 8H3z" />
  </svg>
)
export const IconSpark = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" />
  </svg>
)
