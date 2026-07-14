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

// Traced from the reference badge artwork (filled silhouette, not a stroke
// icon like the others below) — kept as its own transform group instead of
// hand-normalized coordinates so it stays a faithful trace of the source.
export const IconRunner = (p: P) => (
  <svg {...base(p)}>
    <g fill="currentColor" stroke="none" transform="translate(4.233 2) scale(0.032362 0.032362)">
      <g transform="translate(0,618) scale(0.1,-0.1)">
        <path
          d="M3260 5966 c-140 -30 -244 -86 -346 -186 -101 -99 -171 -227 -198
-362 -19 -90 -20 -139 -5 -228 25 -157 86 -276 199 -391 179 -180 453 -244
698 -163 127 43 273 157 351 277 46 71 91 174 95 221 2 17 7 39 11 49 4 10 5
70 3 135 -4 100 -10 130 -38 206 -18 49 -40 97 -49 106 -9 9 -17 23 -19 31
-11 45 -146 176 -239 230 -122 73 -321 105 -463 75z M2116 4460 c-220 -61
-427 -123 -460 -139 -123 -59 -148 -93 -431 -625 -168 -315 -177 -343 -133
-425 39 -73 148 -114 211 -79 12 7 29 13 37 14 8 2 25 14 36 27 23 27 201 346
206 369 2 7 6 15 10 18 12 9 141 244 141 258 0 6 4 12 8 12 4 0 20 23 36 50
23 42 35 52 73 64 38 12 333 95 578 162 34 9 65 14 69 10 7 -7 3 -17 -240
-596 -91 -217 -173 -422 -182 -455 -37 -143 12 -292 126 -382 41 -33 194 -97
209 -88 5 3 10 1 12 -4 1 -4 158 -61 348 -126 190 -64 370 -126 402 -137 54
-18 56 -20 48 -46 -12 -40 -53 -150 -203 -537 -75 -193 -140 -370 -146 -395
-12 -53 -1 -111 26 -149 25 -35 99 -71 143 -71 46 1 114 32 135 63 17 27 74
166 278 682 l130 330 1 110 c1 124 -11 158 -82 237 -56 62 -108 84 -662 275
-184 63 -354 122 -377 130 l-42 15 23 61 c21 55 364 869 397 940 7 15 17 27
24 27 6 0 164 -104 351 -231 499 -340 515 -349 635 -349 150 0 218 45 437 289
294 326 312 351 312 428 0 78 -72 160 -149 170 -89 12 -136 -24 -371 -287 -47
-52 -117 -128 -156 -169 l-71 -74 -257 174 c-141 96 -355 240 -474 321 -308
208 -376 239 -535 238 -60 -1 -140 -20 -471 -110z M1893 2555 c-18 -8 -42 -29
-53 -47 -39 -62 -169 -331 -164 -340 3 -4 1 -8 -4 -8 -4 0 -77 -143 -161 -319
l-153 -318 -351 -324 c-194 -178 -351 -327 -349 -331 1 -4 -2 -7 -7 -6 -17 6
-411 -372 -432 -414 -25 -48 -23 -121 5 -162 53 -82 178 -107 252 -51 43 33
187 160 339 300 55 51 217 199 360 330 515 472 453 399 600 700 329 671 375
772 375 833 0 61 -42 131 -93 155 -42 20 -120 21 -164 2z"
        />
      </g>
    </g>
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
export const IconEye = (p: P) => (
  <svg {...base(p)}>
    <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)
export const IconEyeOff = (p: P) => (
  <svg {...base(p)}>
    <path d="M9.9 4.24A10.94 10.94 0 0112 4c6 0 10 7 10 7a17.7 17.7 0 01-3.16 4.2M6.6 6.6C4.14 8.24 2 11 2 11s4 7 10 7a10.9 10.9 0 004.24-.86" />
    <path d="M10.58 10.58a3 3 0 004.24 4.24" />
    <path d="M3 3l18 18" />
  </svg>
)
