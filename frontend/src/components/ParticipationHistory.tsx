import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Gender, Group, ParticipationEntry } from '../types'
import { formatDate, formatDistance, formatDuration, formatPace } from '../lib/format'
import { attendanceApi } from '../api/attendance'
import { groupsApi } from '../api/groups'
import { ManualResultForm } from './ManualResultForm'
import { IconFlag } from './ui/icons'

interface Props {
  history: ParticipationEntry[]
  /** Show "add result" controls — only true when viewing your own history. */
  editable?: boolean
  gender?: Gender | null
  onResultSubmitted?: () => void
}

export function ParticipationHistory({
  history,
  editable = false,
  gender = null,
  onResultSubmitted,
}: Props) {
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
          gender={gender}
          onResultSubmitted={onResultSubmitted}
        />
      ))}
    </ul>
  )
}

function HistoryRow({
  entry: h,
  editable,
  gender,
  onResultSubmitted,
}: {
  entry: ParticipationEntry
  editable: boolean
  gender: Gender | null
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
  // Only a *rejected* record can move to a different group — one with no
  // result yet (e.g. CSV-placed) is left as is, same rule the backend
  // enforces (see _group_is_fixed in backend/app/api/signups.py).
  const canSwitchGroup = rejected

  const [groupId, setGroupId] = useState(h.group_id)
  const [groups, setGroups] = useState<Group[] | null>(null)
  const [switching, setSwitching] = useState(false)
  const startSwitching = async () => {
    setSwitching(true)
    if (groups) return
    try {
      setGroups((await groupsApi.list(h.event_id)).filter((g) => g.has_started))
    } catch {
      setGroups([])
    }
  }
  // The group picker only makes sense while the form for *this* row is open —
  // reset it each time the row is closed so reopening starts fresh.
  useEffect(() => {
    if (!open) {
      setGroupId(h.group_id)
      setGroups(null)
      setSwitching(false)
    }
  }, [open, h.group_id])

  const rowRef = useRef<HTMLLIElement>(null)
  const didRunLabel = gender === 'female' ? 'Бегала' : gender === 'male' ? 'Бегал' : 'Бегал(а)'

  return (
    <li ref={rowRef} className="rounded-xl2 border border-ink/[0.08] bg-white shadow-card">
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
          <div className="hidden shrink-0 items-center gap-2.5 sm:flex">
            {editable && h.moderation_status === 'approved' && (
              <span className="chip bg-volt/25 text-ink">Подтверждён</span>
            )}
            {editable && h.moderation_status === 'pending' && (
              <span className="chip bg-ink/10 text-ink-600">На проверке</span>
            )}
            <div className="text-right">
              <div className="font-mono text-sm font-semibold tabular text-ink">
                {formatDuration(h.duration_seconds)}
              </div>
              <div className="font-mono text-[0.65rem] tabular text-clay">
                {formatPace(h.pace_seconds_per_km)} · {formatDistance(h.distance_km)}
              </div>
            </div>
          </div>
        )}
      </div>
      {open && needsResult && (
        <div className="border-t border-ink/[0.06] bg-paper-soft/40 p-4">
          <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-600">
            {switching && groups ? (
              <label className="flex items-center gap-2">
                Группа, в которой вы бежали:
                <select
                  value={groupId}
                  onChange={(ev) => setGroupId(Number(ev.target.value))}
                  className="rounded-lg border border-ink/15 bg-white px-2 py-1 text-sm text-ink"
                >
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                      {g.location ? ` · ${g.location}` : ''}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <>
                <span>
                  Группа: <b className="text-ink">{h.group_name}</b>
                </span>
                {canSwitchGroup && (
                  <button
                    type="button"
                    onClick={startSwitching}
                    className="text-signal hover:underline"
                  >
                    {switching ? 'Загрузка…' : `${didRunLabel} в другой группе?`}
                  </button>
                )}
              </>
            )}
          </div>
          <ManualResultForm
            onSubmit={(d) => attendanceApi.submitGroupResult(groupId, d)}
            onDone={() => {
              setOpen(false)
              onResultSubmitted?.()
            }}
          />
        </div>
      )}
    </li>
  )
}
