import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { Spinner } from './ui/Spinner'

export interface ManualResultData {
  distance_km: number
  duration_seconds: number
  image: File
}

function parseDuration(input: string): number {
  const parts = input.split(':').map((p) => Number(p.trim()))
  if (parts.some((p) => Number.isNaN(p))) return 0
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 1) return parts[0]
  return 0
}

/** Manual result entry: distance + time + a required screenshot. GPX/URL upload
 * is gone for runners — the screenshot (with the fields listed below visible) is
 * the evidence an admin moderates. */
export function ManualResultForm({
  onSubmit,
  onDone,
}: {
  onSubmit: (data: ManualResultData) => Promise<unknown>
  onDone?: () => void
}) {
  const [distance, setDistance] = useState('')
  const [duration, setDuration] = useState('')
  const [image, setImage] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const distanceKm = Number(distance.replace(',', '.'))
    const durationSeconds = parseDuration(duration)
    if (!distanceKm || !durationSeconds) {
      setError('Укажите дистанцию (км) и время (чч:мм:сс)')
      return
    }
    if (!image) {
      setError('Прикрепите скриншот пробежки')
      return
    }
    setBusy(true)
    try {
      await onSubmit({ distance_km: distanceKm, duration_seconds: durationSeconds, image })
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
            onChange={(e) => setDistance(e.target.value)}
            placeholder="33.2"
            inputMode="decimal"
            className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold text-ink-600">Время, чч:мм:сс</label>
          <input
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            placeholder="3:10:00"
            className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm"
          />
        </div>
      </div>
      <div>
        <label className="mb-1 block text-xs font-semibold text-ink-600">
          Скриншот пробежки *
        </label>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(e) => setImage(e.target.files?.[0] ?? null)}
          className="block w-full text-sm text-ink-600 file:mr-3 file:rounded-full file:border file:border-ink/15 file:bg-white file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-ink-600 hover:file:border-ink/30"
        />
        <div className="mt-2 rounded-lg border border-ink/10 bg-white/60 p-2.5 text-xs text-ink-600">
          На скриншоте должны быть чётко видны:
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            <li>дата и время старта</li>
            <li>дистанция</li>
            <li>время пробежки</li>
            <li>трек маршрута</li>
          </ul>
          <span className="mt-1.5 block text-clay">
            Без этих данных результат не примут на модерации.
          </span>
        </div>
      </div>

      {error && <p className="text-xs text-signal-600">{error}</p>}

      <button type="submit" disabled={busy} className="btn-primary btn-sm">
        {busy ? <Spinner className="h-4 w-4" /> : 'Отправить на проверку'}
      </button>
      <p className="text-xs text-clay">Ручной ввод всегда проверяется администратором.</p>
    </form>
  )
}
