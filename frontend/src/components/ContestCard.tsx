import { Link } from 'react-router-dom'
import { media } from '../api/client'
import { formatDate, formatTime } from '../lib/format'
import { IconArrow, IconTrophy } from './ui/icons'
import type { ContestPhase, ContestSummary } from '../types'

const PHASE_LABEL: Record<ContestPhase, string> = {
  draft: 'Скоро',
  upcoming: 'Скоро начнётся',
  submissions_open: 'Приём заявок открыт',
  submissions_closed: 'Приём заявок завершён',
  voting_open: 'Идёт голосование',
  voting_closed: 'Итоги',
}

export function ContestCard({ contest, index }: { contest: ContestSummary; index: number }) {
  const cover = media(contest.cover_image)
  return (
    <Link
      to={`/contests/${contest.id}`}
      className="group relative flex flex-col overflow-hidden rounded-xl2 border border-ink/[0.08] bg-white shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-lift animate-fade-up"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-paper-deep">
        {cover ? (
          <img
            src={cover}
            alt={contest.title}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-ink text-paper/20">
            <IconTrophy width={64} height={64} />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-ink/70 via-ink/5 to-transparent" />
        <span
          className={`absolute left-4 top-4 chip ${
            contest.phase === 'submissions_open' || contest.phase === 'voting_open'
              ? 'bg-volt text-ink'
              : 'bg-paper/90 text-ink-600'
          }`}
        >
          {PHASE_LABEL[contest.phase]}
        </span>
      </div>
      <div className="flex flex-1 flex-col p-5">
        <h3 className="font-display text-xl leading-tight text-ink transition-colors group-hover:text-signal">
          {contest.title}
        </h3>
        {contest.submissions_open_at && (
          <p className="mt-2 text-sm text-clay">
            Приём заявок с{' '}
            {formatDate(contest.submissions_open_at, { day: 'numeric', month: 'long' })}, в{' '}
            {formatTime(contest.submissions_open_at)}
          </p>
        )}
        <span className="mt-auto inline-flex items-center gap-1.5 pt-5 font-mono text-xs uppercase tracking-[0.16em] text-signal">
          Подробнее
          <IconArrow width={13} height={13} className="transition-transform group-hover:translate-x-1" />
        </span>
      </div>
    </Link>
  )
}
