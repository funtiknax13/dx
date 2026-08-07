import { useEffect } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  src: string
  alt?: string
  caption?: string
  onClose: () => void
}

/** Full-screen enlarged view of a single image (e.g. an avatar) — click the
 * backdrop or press Escape to close.
 *
 * Rendered through a portal to <body>: a `position: fixed` overlay is contained
 * by any ancestor with a `transform` (e.g. the rating podium's hover
 * translate), which would confine and flicker it — the portal escapes that. */
export function ImageLightbox({ src, alt = '', caption, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  return createPortal(
    <div
      className="fixed inset-0 z-[60] grid place-items-center bg-ink/85 p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <figure
        className="flex max-h-full max-w-full flex-col items-center gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={src}
          alt={alt}
          className="max-h-[78vh] max-w-full rounded-xl2 object-contain shadow-lift"
        />
        {caption && <figcaption className="font-display text-base text-paper">{caption}</figcaption>}
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-paper/30 bg-white/10 px-4 py-1.5 text-xs font-semibold text-paper transition hover:bg-white/20"
        >
          Закрыть
        </button>
      </figure>
    </div>,
    document.body,
  )
}
