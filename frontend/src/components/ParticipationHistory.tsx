import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { ParticipationEntry } from '../types'
import { formatDate, formatDistance, formatDuration, formatPace } from '../lib/format'
import { attendanceApi } from '../api/attendance'
import { ApiError } from '../api/client'
import { IconFlag } from './ui/icons'
import { Spinner } from './ui/Spinner'

interface Props {
  history: ParticipationEntry[]
  /** Show "add result" controls — only true when viewing your own history. */
  editable?: boolean
  onResultSubmitted?: () => void
}

export function ParticipationHistory({ history, editable = false, onResultSubmitted }: Props) {
  if (!history.length) {
    return (
      <div className="rounded-xl2 border border-dashed border-ink/15 bg-white/50 px-6 py-12 text-center">
        <IconFlag className="mx-auto mb-3 text-clay" width={26} height={26} />
        <p className="font-display text-lg text-ink">Пока нет пробежек</p>
        <p className="mt-1 text-sm text-ink-600">
          Здесь появятся события, в которых бегун принял участие.
        </p>
      </div>
    )
  }

  return (
    <ul className="space-y-3">
      {history.map((h) => (
        <HistoryRow
          key={h.attendance_id}
          entry={h}
          editable={editable}
          onResultSubmitted={onResultSubmitted}
        />
      ))}
    </ul>
  )
}

function HistoryRow({
  entry: h,
  editable,
  onResultSubmitted,
}: {
  entry: ParticipationEntry
  editable: boolean
  onResultSubmitted?: () => void
}) {
  const [open, setOpen] = useState(false)
  const finished = h.finish_status === 'finished'
  const needsResult = editable && h.has_result === false

  return (
    <li className="rounded-xl2 border border-ink/[0.08] bg-white shadow-card">
      <div className="flex items-center gap-4 p-4">
        <span
          className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl font-display text-xs ${
            finished ? 'bg-ink text-paper' : 'bg-ink/10 text-ink-600'
          }`}
        >
          {finished ? h.place ?? '✓' : 'DNF'}
        </span>
        <div className="min-w-0 flex-1">
          <Link
            to={`/events/${h.event_id}`}
            className="block truncate font-semibold text-ink hover:text-signal"
          >
            {h.event_title}
          </Link>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-600">
            <Link to={`/groups/${h.group_id}`} className="hover:text-signal">
              {h.group_name}
            </Link>
            <span className="text-clay">
              {formatDate(h.date, { day: 'numeric', month: 'short', year: 'numeric' })}
            </span>
          </div>
        </div>
        {needsResult ? (
          <button
            onClick={() => setOpen((v) => !v)}
            className="btn-primary btn-sm shrink-0"
            type="button"
          >
            {open ? 'Закрыть' : 'Добавить результат'}
          </button>
        ) : (
          <div className="hidden shrink-0 text-right sm:block">
            <div className="font-mono text-sm font-semibold tabular text-ink">
              {formatDuration(h.duration_seconds)}
            </div>
            <div className="font-mono text-[0.65rem] tabular text-clay">
              {formatPace(h.pace_seconds_per_km)} · {formatDistance(h.distance_km)}
            </div>
          </div>
        )}
      </div>
      {open && needsResult && (
        <ResultForm
          attendanceId={h.attendance_id}
          onDone={() => {
            setOpen(false)
            onResultSubmitted?.()
          }}
        />
      )}
    </li>
  )
}

function ResultForm({ attendanceId, onDone }: { attendanceId: number; onDone: () => void }) {
  const [mode, setMode] = useState<'file' | 'manual'>('file')
  const [distance, setDistance] = useState('')
  const [duration, setDuration] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'file') {
        if (!file) {
          setError('Выберите файл GPX или FIT')
          return
        }
        await attendanceApi.submitResultFile(attendanceId, file)
      } else {
        const distanceKm = Number(distance.replace(',', '.'))
        const durationSeconds = parseDuration(duration)
        if (!distanceKm || !durationSeconds) {
          setError('Укажите дистанцию (км) и время (чч:мм:сс)')
          return
        }
        await attendanceApi.submitResultManual(attendanceId, {
          distance_km: distanceKm,
          duration_seconds: durationSeconds,
        })
      }
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить результат')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="border-t border-ink/[0.06] bg-paper-soft/40 p-4">
      <div className="mb-3 flex gap-2">
        <button
          type="button"
          onClick={() => setMode('file')}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold ${mode === 'file' ? 'bg-ink text-paper' : 'border border-ink/10 text-ink-600'}`}
        >
          Загрузить GPX/FIT
        </button>
        <button
          type="button"
          onClick={() => setMode('manual')}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold ${mode === 'manual' ? 'bg-ink text-paper' : 'border border-ink/10 text-ink-600'}`}
        >
          Ввести вручную
        </button>
      </div>

      {mode === 'file' ? (
        <input
          type="file"
          accept=".gpx,.fit"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full text-sm text-ink-600 file:mr-3 file:rounded-full file:border-0 file:bg-ink file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-paper"
        />
      ) : (
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
      )}

      {error && <p className="mt-2 text-xs text-signal-600">{error}</p>}

      <button type="submit" disabled={busy} className="btn-primary btn-sm mt-3">
        {busy ? <Spinner className="h-4 w-4" /> : 'Отправить на проверку'}
      </button>
      <p className="mt-2 text-xs text-clay">
        Результат из файла с подходящей дистанцией и временем старта засчитывается сразу, иначе —
        после проверки администратором. Ручной ввод всегда проверяется вручную.
      </p>
    </form>
  )
}

function parseDuration(input: string): number {
  const parts = input.split(':').map((p) => Number(p.trim()))
  if (parts.some((p) => Number.isNaN(p))) return 0
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 1) return parts[0]
  return 0
}
