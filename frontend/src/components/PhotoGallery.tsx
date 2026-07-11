import { useEffect, useState } from 'react'
import { media } from '../api/client'
import type { EventPhoto } from '../types'
import { IconX } from './ui/icons'

export function PhotoGallery({ photos }: { photos: EventPhoto[] }) {
  const [active, setActive] = useState<number | null>(null)

  useEffect(() => {
    if (active == null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setActive(null)
      if (e.key === 'ArrowRight') setActive((i) => (i == null ? i : (i + 1) % photos.length))
      if (e.key === 'ArrowLeft')
        setActive((i) => (i == null ? i : (i - 1 + photos.length) % photos.length))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, photos.length])

  if (!photos.length) return null

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {photos.map((photo, i) => (
          <button
            key={photo.id}
            onClick={() => setActive(i)}
            className="group relative aspect-square overflow-hidden rounded-xl bg-paper-deep"
          >
            <img
              src={media(photo.thumbnail_url ?? photo.url)}
              alt={photo.caption ?? ''}
              loading="lazy"
              className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-110"
            />
            <span className="absolute inset-0 bg-ink/0 transition-colors group-hover:bg-ink/15" />
          </button>
        ))}
      </div>

      {active != null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/90 p-4 backdrop-blur animate-fade-in"
          onClick={() => setActive(null)}
        >
          <button
            className="absolute right-4 top-4 grid h-11 w-11 place-items-center rounded-full bg-paper/10 text-paper hover:bg-paper/20"
            onClick={() => setActive(null)}
            aria-label="Закрыть"
          >
            <IconX />
          </button>
          <figure className="max-h-full max-w-4xl" onClick={(e) => e.stopPropagation()}>
            <img
              src={media(photos[active].url)}
              alt={photos[active].caption ?? ''}
              className="max-h-[80vh] w-auto rounded-xl2 object-contain"
            />
            {photos[active].caption && (
              <figcaption className="mt-3 text-center font-mono text-sm text-paper/70">
                {photos[active].caption}
              </figcaption>
            )}
          </figure>
        </div>
      )}
    </>
  )
}
