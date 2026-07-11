import { Link } from 'react-router-dom'
import type { Group } from '../types'
import { formatTime, paceRange, plural } from '../lib/format'
import { IconArrow, IconClock, IconPin, IconRoute } from './ui/icons'

export function GroupCard({ group, index = 0 }: { group: Group; index?: number }) {
  const pace = paceRange(group.pace_min, group.pace_max)

  return (
    <Link
      to={`/groups/${group.id}`}
      className="group flex items-stretch gap-4 rounded-xl2 border border-ink/[0.08] bg-white p-4 shadow-card transition-all hover:-translate-y-0.5 hover:border-signal/40 hover:shadow-lift animate-fade-up sm:p-5"
      style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}
    >
      {/* Distance code block — timing-card feel */}
      <div className="flex w-20 shrink-0 flex-col items-center justify-center rounded-xl bg-ink px-2 py-3 text-center text-paper sm:w-24">
        <span className="font-display text-xl leading-none text-volt sm:text-2xl">
          {group.distance_code ?? '—'}
        </span>
        {group.target_distance_km != null && (
          <span className="mt-1 font-mono text-[0.65rem] text-paper/60 tabular">
            {group.target_distance_km} км
          </span>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col justify-center">
        <h3 className="truncate font-display text-lg leading-tight text-ink transition-colors group-hover:text-signal">
          {group.name}
        </h3>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-600">
          {group.location && (
            <span className="inline-flex items-center gap-1.5">
              <IconPin width={14} height={14} className="text-signal" />
              <span className="truncate">{group.location}</span>
            </span>
          )}
          {pace && (
            <span className="inline-flex items-center gap-1.5 font-mono tabular">
              <IconRoute width={14} height={14} className="text-signal" />
              {pace} /км
            </span>
          )}
          {group.start_time && (
            <span className="inline-flex items-center gap-1.5 font-mono tabular">
              <IconClock width={14} height={14} className="text-signal" />
              {formatTime(group.start_time)}
            </span>
          )}
        </div>
        {(group.signup_count != null || group.finisher_count != null) && (
          <div className="mt-2 flex flex-wrap gap-2">
            {group.signup_count != null && (
              <span className="chip bg-paper-deep text-ink-600">
                {group.signup_count} {plural(group.signup_count, 'запись', 'записи', 'записей')}
              </span>
            )}
            {group.finisher_count != null && group.finisher_count > 0 && (
              <span className="chip bg-ink/10 text-ink">
                {group.finisher_count} финишир.
              </span>
            )}
            {group.has_route_gpx && (
              <span className="chip bg-signal-wash text-signal-600">маршрут</span>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center">
        <span className="grid h-9 w-9 place-items-center rounded-full border border-ink/10 text-ink transition-all group-hover:border-signal group-hover:bg-signal group-hover:text-white">
          <IconArrow width={16} height={16} />
        </span>
      </div>
    </Link>
  )
}
