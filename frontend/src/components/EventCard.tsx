import { Link } from 'react-router-dom'
import { media } from '../api/client'
import type { EventSummary } from '../types'
import { formatDate, isPast, plural } from '../lib/format'
import { IconArrow, IconCalendar, IconPin, IconRunner } from './ui/icons'

export function EventCard({ event, index = 0 }: { event: EventSummary; index?: number }) {
  const cover = media(event.cover_url)
  const past = isPast(event.date)

  return (
    <Link
      to={`/events/${event.id}`}
      className="group relative flex flex-col overflow-hidden rounded-xl2 border border-ink/[0.08] bg-white shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-lift animate-fade-up"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-paper-deep">
        {cover ? (
          <img
            src={cover}
            alt={event.title}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-ink text-paper/20">
            <IconRunner width={64} height={64} />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-ink/70 via-ink/5 to-transparent" />
        <span
          className={`absolute left-4 top-4 chip ${
            past ? 'bg-paper/90 text-ink-600' : 'bg-volt text-ink'
          }`}
        >
          {past ? 'Прошло' : 'Скоро'}
        </span>
        <div className="absolute bottom-3 left-4 right-4 flex items-center gap-2 text-paper">
          <IconCalendar width={16} height={16} className="opacity-90" />
          <span className="font-mono text-xs font-medium tabular">{formatDate(event.date)}</span>
        </div>
      </div>

      <div className="flex flex-1 flex-col p-5">
        <h3 className="font-display text-xl leading-tight text-ink transition-colors group-hover:text-signal">
          {event.title}
        </h3>
        {event.location_summary && (
          <p className="mt-2 flex items-center gap-1.5 text-sm text-ink-600">
            <IconPin width={15} height={15} className="text-signal" />
            <span className="line-clamp-1">{event.location_summary}</span>
          </p>
        )}
        {event.description && (
          <p className="mt-2 line-clamp-2 text-sm text-clay">{event.description}</p>
        )}

        <div className="mt-auto flex items-center justify-between pt-5">
          <div className="flex items-center gap-4 font-mono text-xs text-ink-600">
            {typeof event.group_count === 'number' && (
              <span className="tabular">
                {event.group_count} {plural(event.group_count, 'группа', 'группы', 'групп')}
              </span>
            )}
            {typeof event.participant_count === 'number' && (
              <span className="tabular">
                {event.participant_count}{' '}
                {plural(event.participant_count, 'участник', 'участника', 'участников')}
              </span>
            )}
          </div>
          <span className="grid h-9 w-9 place-items-center rounded-full bg-ink text-paper transition-transform group-hover:translate-x-1">
            <IconArrow width={16} height={16} />
          </span>
        </div>
      </div>
    </Link>
  )
}
