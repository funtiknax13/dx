import { useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { Spinner } from './ui/Spinner'

export interface ManualResultData {
  distance_km: number
  duration_seconds: number
  images: File[]
  comment?: string
}

const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const ALLOWED_IMAGE_HINT = 'Файл должен быть в формате JPG, JPEG, PNG или WEBP'
// Backend enforces the same floor (see MIN_MANUAL_PACE_SECONDS_PER_KM in
// app/api/results.py) — this is just the earlier, friendlier check.
const MIN_PACE_SECONDS_PER_KM = 90

/** Digits + a single decimal separator (comma or dot) — strips everything
 * else and any extra separator as you type, so the field can't hold garbage
 * that only surfaces as an error on submit. */
function sanitizeDistanceInput(value: string): string {
  const cleaned = value.replace(/[^\d.,]/g, '')
  const firstSep = cleaned.search(/[.,]/)
  if (firstSep === -1) return cleaned
  return cleaned.slice(0, firstSep + 1) + cleaned.slice(firstSep + 1).replace(/[.,]/g, '')
}

function parseDuration(input: string): number {
  const parts = input.split(':').map((p) => Number(p.trim()))
  if (parts.some((p) => Number.isNaN(p))) return 0
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 1) return parts[0]
  return 0
}

/** Progressive Ч:ММ:СС mask: 1 digit hours, then auto ":", 2 digits minutes,
 * auto ":", 2 digits seconds — a colon is inserted on its own once a segment
 * is full. Typing ':' yourself works too and does the same thing (moves on
 * to the next segment early, e.g. "1" then ":" for a single-digit minute
 * count instead of being forced to pad to "01") rather than silently
 * disappearing, which felt broken. Recomputed from scratch on every
 * keystroke, so backspace/edit-in-the-middle behave normally. */
function formatTimeMask(input: string): string {
  const cleaned = input.replace(/[^\d:]/g, '')
  const maxLen = [1, 2, 2]
  const segments = ['']
  let seg = 0

  for (const ch of cleaned) {
    if (ch === ':') {
      // Only advances when there's something to leave behind, and only up
      // to seconds — an empty or trailing ':' has nothing to do.
      if (seg < 2 && segments[seg] !== '') {
        seg += 1
        segments[seg] = ''
      }
      continue
    }
    if (segments[seg].length < maxLen[seg]) {
      segments[seg] += ch
    } else if (seg < 2) {
      seg += 1
      segments[seg] = ch
    } // else: seconds already full — extra digits are dropped
  }

  return segments.join(':')
}

/** Manual result entry: distance + time + at least one required screenshot.
 * GPX/URL upload is gone for runners — the screenshots (with the fields listed
 * below visible across one or more of them) are the evidence an admin moderates.
 * Several are allowed for when a single screen can't show the date and the track
 * at once. */
export function ManualResultForm({
  onSubmit,
  onDone,
}: {
  onSubmit: (data: ManualResultData) => Promise<unknown>
  onDone?: () => void
}) {
  const [distance, setDistance] = useState('')
  const [duration, setDuration] = useState('')
  const [images, setImages] = useState<File[]>([])
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = (files: FileList | null) => {
    if (!files) return
    const picked = Array.from(files)
    const accepted = picked.filter((f) => ALLOWED_IMAGE_TYPES.includes(f.type))
    setError(picked.length > accepted.length ? ALLOWED_IMAGE_HINT : null)
    setImages((prev) => {
      // Dedupe by name+size so re-picking the same file doesn't double it.
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`))
      return [...prev, ...accepted.filter((f) => !seen.has(`${f.name}:${f.size}`))]
    })
    if (inputRef.current) inputRef.current.value = '' // allow re-selecting the same file
  }

  const removeAt = (i: number) => setImages((prev) => prev.filter((_, idx) => idx !== i))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const distanceKm = Number(distance.replace(',', '.'))
    const durationSeconds = parseDuration(duration)
    if (!distanceKm) {
      setError('Укажите дистанцию (км)')
      return
    }
    if (!durationSeconds) {
      setError('Укажите время (ч:мм:сс)')
      return
    }
    const tp = duration.split(':').map(Number)
    if ((tp.length >= 2 && tp[1] >= 60) || (tp.length >= 3 && tp[2] >= 60)) {
      setError('Минуты и секунды должны быть меньше 60')
      return
    }
    // Faster than this isn't a real running pace — almost always the H:MM:SS
    // field got misread as M:SS (e.g. "2:05" typed meaning 2h05m, parsed as
    // 2m05s). Catch it here with a clear message instead of silently saving
    // a nonsense result for a moderator to puzzle over later.
    if (durationSeconds / distanceKm < MIN_PACE_SECONDS_PER_KM) {
      setError('Время указано некорректно — проверьте формат Ч:ММ:СС (например, 2 часа 5 минут — это 2:05:00, а не 2:05)')
      return
    }
    if (images.length === 0) {
      setError('Прикрепите хотя бы один скриншот пробежки')
      return
    }
    setBusy(true)
    try {
      await onSubmit({
        distance_km: distanceKm,
        duration_seconds: durationSeconds,
        images,
        comment: comment.trim() || undefined,
      })
      onDone?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить результат')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-semibold text-ink-600">Дистанция, км</label>
          <input
            value={distance}
            onChange={(e) => setDistance(sanitizeDistanceInput(e.target.value))}
            placeholder="33.2"
            inputMode="decimal"
            className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold text-ink-600">Время, ч:мм:сс</label>
          <input
            value={duration}
            onChange={(e) => setDuration(formatTimeMask(e.target.value))}
            placeholder="0:00:00"
            inputMode="numeric"
            className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm"
          />
        </div>
      </div>
      <div>
        <label className="mb-1 block text-xs font-semibold text-ink-600">
          Скриншоты пробежки *
        </label>
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          onChange={(e) => addFiles(e.target.files)}
          className="block w-full text-sm text-ink-600 file:mr-3 file:rounded-full file:border file:border-ink/15 file:bg-white file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-ink-600 hover:file:border-ink/30"
        />

        {images.length > 0 && (
          <ul className="mt-2 space-y-1">
            {images.map((f, i) => (
              <li
                key={`${f.name}:${f.size}:${i}`}
                className="flex items-center justify-between gap-2 rounded-lg border border-ink/10 bg-white px-2.5 py-1.5 text-xs"
              >
                <span className="truncate text-ink-600">{f.name}</span>
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  className="shrink-0 rounded px-1.5 text-clay hover:text-signal"
                  aria-label="Убрать"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-2 rounded-lg border border-ink/10 bg-white/60 p-2.5 text-xs text-ink-600">
          На скриншотах (можно несколько) должны быть чётко видны:
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            <li>дата и время старта</li>
            <li>дистанция</li>
            <li>время пробежки</li>
            <li>трек маршрута</li>
          </ul>
          <span className="mt-1.5 block text-clay">
            Если на одном экране всё не помещается — приложите несколько. Без этих данных
            результат не примут на модерации.
          </span>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-semibold text-ink-600">
          Комментарий <span className="font-normal text-clay">(необязательно)</span>
        </label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value.slice(0, 1000))}
          rows={2}
          placeholder="Если пробежка не совпадает с группой — поясните: отвалился GPS, бежал на старт от дома и т.п."
          className="w-full resize-y rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm"
        />
      </div>

      {error && <p className="text-xs text-danger-600">{error}</p>}

      <button type="submit" disabled={busy} className="btn-primary btn-sm">
        {busy ? <Spinner className="h-4 w-4" /> : 'Отправить на проверку'}
      </button>
      <p className="text-xs text-clay">Ручной ввод всегда проверяется администратором.</p>
    </form>
  )
}
