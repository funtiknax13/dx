import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { ParticipationEntry } from '../types'
import { formatDate, formatDistance, formatDuration, formatPace } from '../lib/format'
import { attendanceApi } from '../api/attendance'
import { ManualResultForm } from './ManualResultForm'
import { IconFlag } from './ui/icons'

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
  const rejected = h.moderation_status === 'rejected'
  // The upload form is offered only when there's nothing final to protect: no
  // result yet, or a rejected one to redo. A pending result is awaiting
  // moderation and an approved one is settled — neither can be re-uploaded
  // (see _check_resubmit_allowed in backend/app/api/results.py).
  const needsResult = editable && (h.has_result === false || rejected)

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
          <div className="flex shrink-0 items-center gap-2">
            {rejected && (
              <span className="chip bg-signal/10 text-signal-600">Отклонён</span>
            )}
            <button
              onClick={() => setOpen((v) => !v)}
              className="btn-primary btn-sm"
              type="button"
            >
              {open ? 'Закрыть' : rejected ? 'Загрузить заново' : 'Добавить результат'}
            </button>
          </div>
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
  return (
    <div className="border-t border-ink/[0.06] bg-paper-soft/40 p-4">
      <ManualResultForm
        onSubmit={(d) => attendanceApi.submitResultManual(attendanceId, d)}
        onDone={onDone}
      />
    </div>
  )
}
