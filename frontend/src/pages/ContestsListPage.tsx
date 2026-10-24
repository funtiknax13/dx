import { Link } from 'react-router-dom'
import { contestsApi } from '../api/contests'
import { media } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { formatDate, formatTime, plural } from '../lib/format'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconArrow, IconTrophy } from '../components/ui/icons'
import type { ContestPhase, ContestSummary } from '../types'

const PHASE_LABEL: Record<ContestPhase, string> = {
  draft: 'Скоро',
  upcoming: 'Скоро начнётся',
  submissions_open: 'Приём заявок открыт',
  submissions_closed: 'Приём заявок завершён',
  voting_open: 'Идёт голосование',
  voting_closed: 'Итоги',
}

export function ContestsListPage() {
  const { data, loading, error, reload } = useAsync(() => contestsApi.list(), [])
  const activeCount = data?.filter((c) => c.phase !== 'voting_closed').length ?? 0

  return (
    <div>
      <header className="relative overflow-hidden bg-ink text-paper">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            backgroundImage:
              'radial-gradient(55% 80% at 90% 0%, rgba(255,255,255,0.14), transparent 60%), radial-gradient(50% 70% at 5% 100%, rgba(255,255,255,0.07), transparent 60%)',
          }}
        />
        <div className="stripe absolute inset-x-0 top-0 h-1.5" />
        <div className="container-page relative py-14 sm:py-16">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="eyebrow text-volt">
              <IconTrophy width={16} height={16} /> Активности
            </span>
            {data && data.length > 0 && (
              <span className="chip border border-paper/15 bg-paper/[0.06] text-paper/60">
                {activeCount > 0
                  ? `${activeCount} ${plural(activeCount, 'активный', 'активных', 'активных')}`
                  : `${data.length} ${plural(data.length, 'конкурс', 'конкурса', 'конкурсов')}`}
              </span>
            )}
          </div>
          <h1 className="mt-3 font-display text-4xl leading-tight sm:text-5xl">Конкурсы</h1>
          <p className="mt-3 max-w-xl text-paper/65">
            Маршруты, фото и другие вызовы от сообщества — с заявками и голосованием участников.
          </p>
        </div>
      </header>

      <section className="container-page py-12 sm:py-16">
        {loading ? (
          <PageLoader />
        ) : error ? (
          <StatePanel
            tone="error"
            title="Не удалось загрузить конкурсы"
            description={error}
            icon={<IconTrophy />}
            action={
              <button onClick={reload} className="btn-ink">
                Повторить
              </button>
            }
          />
        ) : !data || data.length === 0 ? (
          <StatePanel
            title="Пока нет ни одного конкурса"
            description="Загляните позже — сообщество периодически объявляет конкурсы с голосованием."
            icon={<IconTrophy />}
          />
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((c, i) => (
              <ContestCard key={c.id} contest={c} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function ContestCard({ contest, index }: { contest: ContestSummary; index: number }) {
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
