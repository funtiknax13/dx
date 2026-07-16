import { Link } from 'react-router-dom'
import type { Protocol, ProtocolRow } from '../types'
import { Avatar } from './ui/Avatar'
import { formatDistance, formatDuration, formatPace } from '../lib/format'
import { IconFlag } from './ui/icons'

function medal(place?: number | null) {
  // Rank communicated by value, not hue: 1st = ink black, 2nd/3rd a step lighter each.
  if (place === 1) return 'bg-ink text-paper'
  if (place === 2) return 'bg-[#B4B4AF] text-ink'
  if (place === 3) return 'bg-[#D6D6D2] text-ink'
  return 'bg-ink text-paper'
}

function RunnerCell({ row }: { row: ProtocolRow }) {
  const name = row.runner_name
  const inner = (
    <span className="flex items-center gap-3">
      <Avatar
        first={name.split(' ')[0]}
        last={name.split(' ')[1]}
        src={row.avatar_url}
        size="sm"
      />
      <span className="min-w-0">
        <span className="flex items-center gap-1.5">
          <span className="truncate font-semibold text-ink">{name}</span>
          {row.latest_achievement != null && (
            <span
              className="inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-full border border-signal px-0.5 font-display text-[0.55rem] leading-none text-signal"
              title={`Достижение: ${row.latest_achievement} DX`}
            >
              {row.latest_achievement}
            </span>
          )}
        </span>
        {row.runner_id == null && (
          <span className="font-mono text-[0.65rem] uppercase tracking-wide text-clay">
            без аккаунта
          </span>
        )}
      </span>
    </span>
  )
  return row.runner_id != null ? (
    <Link to={`/users/${row.runner_id}`} className="hover:text-signal">
      {inner}
    </Link>
  ) : (
    inner
  )
}

function ProtocolRowLine({ row }: { row: ProtocolRow }) {
  const isDnf = row.finish_status === 'dnf'
  const hasTime = row.duration_seconds != null
  return (
    <tr className="border-b border-ink/[0.06] transition-colors hover:bg-signal-wash/30">
      <td className="py-3 pl-4 pr-2">
        <span
          className={`grid h-8 w-8 place-items-center rounded-full font-display text-sm ${
            isDnf ? 'bg-ink/10 text-ink-600' : medal(row.place)
          }`}
        >
          {row.place ?? '—'}
        </span>
      </td>
      <td className="py-3 pr-3">
        <RunnerCell row={row} />
      </td>
      <td className="py-3 pr-3 text-right font-mono text-sm font-semibold tabular text-ink">
        {isDnf ? (
          <span className="text-xs uppercase tracking-wide text-clay">DNF</span>
        ) : hasTime ? (
          formatDuration(row.duration_seconds)
        ) : (
          <span className="text-xs uppercase tracking-wide text-clay">пробежал</span>
        )}
      </td>
      <td className="hidden py-3 pr-3 text-right font-mono text-sm tabular text-ink-600 sm:table-cell">
        {formatPace(row.pace_seconds_per_km)}
      </td>
      <td className="hidden py-3 pr-4 text-right font-mono text-sm tabular text-ink-600 md:table-cell">
        {formatDistance(row.distance_km)}
      </td>
    </tr>
  )
}

export function ProtocolTable({ protocol }: { protocol: Protocol }) {
  const { finishers, pending, dnf } = protocol
  const rows = [...finishers, ...pending, ...dnf]

  if (rows.length === 0) {
    return (
      <div className="rounded-xl2 border border-dashed border-ink/15 bg-white/50 px-6 py-12 text-center">
        <IconFlag className="mx-auto mb-3 text-clay" width={28} height={28} />
        <p className="font-display text-lg text-ink">Протокол пока пуст</p>
        <p className="mt-1 text-sm text-ink-600">
          Результаты появятся после того, как администратор загрузит список участников.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl2 border border-ink/[0.08] bg-white shadow-card">
      {/* Header band */}
      <div className="flex items-center justify-between bg-ink px-4 py-3 text-paper">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-volt">Протокол</span>
        <span className="font-mono text-xs tabular text-paper/60">
          {finishers.length + pending.length} финишировали
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-left">
          <thead>
            <tr className="border-b border-ink/10 bg-paper-soft/60 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-ink-600">
              <th className="py-2.5 pl-4 pr-2 font-semibold">#</th>
              <th className="py-2.5 pr-3 font-semibold">Участник</th>
              <th className="py-2.5 pr-3 text-right font-semibold">Время</th>
              <th className="hidden py-2.5 pr-3 text-right font-semibold sm:table-cell">Темп</th>
              <th className="hidden py-2.5 pr-4 text-right font-semibold md:table-cell">Дист.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <ProtocolRowLine key={row.attendance_id} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
