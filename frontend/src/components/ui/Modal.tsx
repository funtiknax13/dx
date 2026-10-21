import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { IconX } from './icons'

interface Props {
  title: string
  onClose: () => void
  children: ReactNode
  closeDisabled?: boolean
}

/** Generic centered modal (portal to <body>, Escape + backdrop-click to
 * close, body scroll locked while open) — see AvatarCropModal/ImageLightbox
 * for the two prior one-off versions of this same pattern this generalizes. */
export function Modal({ title, onClose, children, closeDisabled = false }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !closeDisabled) onClose()
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose, closeDisabled])

  return createPortal(
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/60 p-4"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget && !closeDisabled) onClose()
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl2 bg-white p-5 shadow-lift sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="font-display text-lg text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={closeDisabled}
            className="rounded-full p-1 text-ink-600 transition hover:bg-ink/5 hover:text-ink disabled:opacity-40"
            aria-label="Закрыть"
          >
            <IconX className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}
