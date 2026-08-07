import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Spinner } from './ui/Spinner'

// Square viewport (CSS px) the user frames the photo inside, and the size of
// the square PNG/JPEG we actually export. The backend still runs its own
// EXIF-fix + square fit as a safety net (see media_service.save_avatar).
const VIEW = 256
const OUTPUT = 512
const MAX_ZOOM = 4

interface Props {
  file: File
  busy?: boolean
  error?: string | null
  onCancel: () => void
  onConfirm: (cropped: File) => void
}

/** Lets the user manually pan/zoom a square crop of their photo before upload —
 * auto-centering alone cropped full-body shots badly (head cut off), so the
 * framing is theirs to choose. */
export function AvatarCropModal({ file, busy = false, error, onCancel, onConfirm }: Props) {
  const imgRef = useRef<HTMLImageElement | null>(null)
  const drag = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })

  // Create AND revoke the object URL in one effect: under React 18 StrictMode
  // a useMemo-created URL gets revoked by the simulated unmount's cleanup and
  // never recreated, leaving <img> pointing at a dead blob (image never loads).
  useEffect(() => {
    const u = URL.createObjectURL(file)
    setUrl(u)
    setNat(null)
    setLoadError(false)
    return () => URL.revokeObjectURL(u)
  }, [file])

  // Cover-fit scale: the smaller side exactly fills VIEW, so the image always
  // covers the square for any zoom >= 1 (no empty corners to drag into view).
  const baseScale = nat ? Math.max(VIEW / nat.w, VIEW / nat.h) : 1
  const scale = baseScale * zoom

  // Keep the image covering the viewport: top-left offset stays within
  // [VIEW - displayedSize, 0] on each axis.
  const clampOffset = (o: { x: number; y: number }, s: number) => {
    if (!nat) return o
    return {
      x: Math.min(0, Math.max(VIEW - nat.w * s, o.x)),
      y: Math.min(0, Math.max(VIEW - nat.h * s, o.y)),
    }
  }

  const onImgLoad = (e: { currentTarget: HTMLImageElement }) => {
    const w = e.currentTarget.naturalWidth
    const h = e.currentTarget.naturalHeight
    if (!w || !h) return
    const bs = Math.max(VIEW / w, VIEW / h)
    setNat({ w, h })
    setZoom(1)
    // Start centered.
    setOffset({ x: (VIEW - w * bs) / 2, y: (VIEW - h * bs) / 2 })
  }

  // Zoom while keeping whatever is under the viewport centre pinned in place.
  const zoomTo = (next: number) => {
    if (!nat) return
    const z = Math.min(MAX_ZOOM, Math.max(1, next))
    const s0 = baseScale * zoom
    const s1 = baseScale * z
    const cx = (VIEW / 2 - offset.x) / s0
    const cy = (VIEW / 2 - offset.y) / s0
    setOffset(clampOffset({ x: VIEW / 2 - cx * s1, y: VIEW / 2 - cy * s1 }, s1))
    setZoom(z)
  }

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { px: e.clientX, py: e.clientY, ox: offset.x, oy: offset.y }
  }
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    setOffset(
      clampOffset({ x: d.ox + (e.clientX - d.px), y: d.oy + (e.clientY - d.py) }, scale),
    )
  }
  const onPointerUp = () => {
    drag.current = null
  }

  const confirm = () => {
    const el = imgRef.current
    if (!nat || !el) return
    const s = baseScale * zoom
    const srcSize = VIEW / s
    const canvas = document.createElement('canvas')
    canvas.width = OUTPUT
    canvas.height = OUTPUT
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(el, -offset.x / s, -offset.y / s, srcSize, srcSize, 0, 0, OUTPUT, OUTPUT)
    canvas.toBlob(
      (blob) => {
        if (blob) onConfirm(new File([blob], 'avatar.jpg', { type: 'image/jpeg' }))
      },
      'image/jpeg',
      0.9,
    )
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onCancel])

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/60 p-4"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel()
      }}
    >
      <div className="w-full max-w-sm rounded-xl2 bg-white p-5 shadow-lift sm:p-6">
        <h2 className="font-display text-lg text-ink">Кадрируйте фото</h2>
        <p className="mt-1 text-xs text-ink-600">
          Перетащите фото и меняйте масштаб — в аватар попадёт то, что внутри круга.
        </p>

        <div
          className="relative mx-auto mt-4 cursor-grab touch-none select-none overflow-hidden rounded-lg bg-ink/5 active:cursor-grabbing"
          style={{ width: VIEW, height: VIEW }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          {url && (
            <img
              ref={imgRef}
              src={url}
              alt=""
              draggable={false}
              onLoad={onImgLoad}
              onError={() => setLoadError(true)}
              style={{
                position: 'absolute',
                left: offset.x,
                top: offset.y,
                width: nat ? nat.w * scale : undefined,
                height: nat ? nat.h * scale : undefined,
                maxWidth: 'none',
                visibility: nat ? 'visible' : 'hidden',
              }}
            />
          )}
          {!nat && !loadError && (
            <div className="absolute inset-0 grid place-items-center">
              <Spinner className="h-6 w-6 text-ink/40" />
            </div>
          )}
          {loadError && (
            <div className="absolute inset-0 grid place-items-center p-4 text-center text-xs text-signal-600">
              Не удалось открыть изображение
            </div>
          )}
          {/* Circular guide — everything outside the inscribed circle is dimmed. */}
          <div
            className="pointer-events-none absolute inset-0 rounded-full ring-2 ring-white/90"
            style={{ boxShadow: '0 0 0 9999px rgba(0,0,0,0.45)' }}
          />
        </div>

        <div className="mt-4 flex items-center gap-3">
          <span className="text-xs font-semibold text-ink-600">Масштаб</span>
          <input
            type="range"
            min={1}
            max={MAX_ZOOM}
            step={0.01}
            value={zoom}
            onChange={(e) => zoomTo(Number(e.target.value))}
            className="flex-1 accent-ink"
            aria-label="Масштаб фото"
          />
        </div>

        {error && <p className="mt-3 text-xs text-signal-600">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onCancel} disabled={busy} className="btn-ghost btn-sm">
            Отмена
          </button>
          <button type="button" onClick={confirm} disabled={busy || !nat} className="btn-primary btn-sm">
            {busy ? <Spinner className="h-4 w-4" /> : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}
