import { useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent } from 'react'
import { media } from '../../api/client'
import { initials } from '../../lib/format'
import { ImageLightbox } from './ImageLightbox'

interface AvatarProps {
  first?: string
  last?: string
  src?: string | null
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  /** When set and there's a real photo, clicking the avatar opens it enlarged
   * in a lightbox (to see who it is). Click is contained — it won't trigger an
   * enclosing link, so the surrounding name can still navigate to the profile. */
  zoomable?: boolean
}

const sizeMap = {
  sm: 'h-8 w-8 text-[0.65rem]',
  md: 'h-11 w-11 text-sm',
  lg: 'h-16 w-16 text-lg',
  xl: 'h-24 w-24 text-2xl sm:h-28 sm:w-28',
}

export function Avatar({ first, last, src, size = 'md', className = '', zoomable = false }: AvatarProps) {
  const url = media(src)
  const [open, setOpen] = useState(false)
  const canZoom = zoomable && !!url

  const openZoom = (e: ReactMouseEvent | ReactKeyboardEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setOpen(true)
  }

  return (
    <div
      className={`relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-ink font-display font-semibold text-volt ring-1 ring-ink/10 ${canZoom ? 'cursor-zoom-in' : ''} ${sizeMap[size]} ${className}`}
      {...(canZoom
        ? {
            role: 'button' as const,
            tabIndex: 0,
            'aria-label': 'Открыть фото',
            onClick: openZoom,
            onKeyDown: (e: ReactKeyboardEvent) => {
              if (e.key === 'Enter' || e.key === ' ') openZoom(e)
            },
          }
        : {})}
    >
      {url ? (
        <img src={url} alt="" className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <span className="tracking-tight">{initials(first, last)}</span>
      )}
      {open && url && (
        <ImageLightbox
          src={url}
          caption={[first, last].filter(Boolean).join(' ') || undefined}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  )
}
