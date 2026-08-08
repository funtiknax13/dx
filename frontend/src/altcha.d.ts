import type { DetailedHTMLProps, HTMLAttributes } from 'react'

// The Altcha web component (registered via `import 'altcha'`) used as a JSX tag.
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'altcha-widget': DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
        challengeurl?: string
        strings?: string
        auto?: string
        hidefooter?: boolean | string
        hidelogo?: boolean | string
      }
    }
  }
}
