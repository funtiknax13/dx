import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ratingApi } from '../api/rating'
import { leaderboardApi } from '../api/leaderboard'
import { useAsync } from '../lib/useAsync'
import { asList } from '../lib/list'
import { fullName, plural } from '../lib/format'
import { Avatar } from '../components/ui/Avatar'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconTrophy } from '../components/ui/icons'
import type { RatingPeriod } from '../types'

type View = 'rating' | 'streak' | 'km'

const VIEWS: [View, string][] = [
  ['rating', 'Рейтинг'],
  ['streak', 'Серия'],
  ['km', 'По километрам'],
]

const PERIODS: [RatingPeriod, string][] = [
  ['all', 'За всё время'],
  ['year', 'За этот год'],
  ['month', 'За этот месяц'],
]

const VIEW_SUBTITLE: Record<View, string> = {
  rating: 'Рейтинг строится по числу завершённых пробежек (finished), подтверждённых администратором. Чем активнее бежишь — тем выше в таблице.',
  streak: 'Топ по текущей серии подряд посещённых DX — считается по любой группе, не только по полным дистанциям.',
  km: 'Топ по суммарному километражу полных DX.',
}

interface DisplayEntry {
  rank: number
  user_id: number
  first_name: string
  last_name: string
  avatar_url?: string | null
  city?: string | null
  value: number
  valueLabel: string
  secondary?: { value: number; label: string }
}

function formatValue(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace('.', ',')
}

export function RatingPage() {
  const [view, setView] = useState<View>('rating')
  const [period, setPeriod] = useState<RatingPeriod>('all')

  const { data, loading, error, reload } = useAsync(async () => {
    if (view === 'rating') {
      const entries = await ratingApi.list(period)
      return entries.map<DisplayEntry>((e) => ({
        rank: e.rank,
        user_id: e.user_id,
        first_name: e.first_name,
        last_name: e.last_name,
        avatar_url: e.avatar_url,
        city: e.city,
        value: e.score,
        valueLabel: 'балл',
        secondary: { value: e.finished_count, label: 'финишей' },
      }))
    }
    // Streak is period-agnostic — always fetched as "all" regardless of the
    // period toggle (which is hidden for this view anyway).
    const entries = await leaderboardApi.list(view, view === 'streak' ? 'all' : period)
    return entries.map<DisplayEntry>((e) => ({
      rank: e.rank,
      user_id: e.user_id,
      first_name: e.first_name,
      last_name: e.last_name,
      avatar_url: e.avatar_url,
      value: e.value,
      valueLabel: view === 'streak' ? 'DX подряд' : 'км',
    }))
  }, [view, period])
  const entries = useMemo(() => asList<DisplayEntry>(data), [data])

  const podium = entries.slice(0, 3)
  const rest = entries.slice(3)
  const hasSecondary = entries.some((e) => e.secondary)

  return (
    <div>
      <header className="relative overflow-hidden bg-ink text-paper">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            backgroundImage:
              'radial-gradient(50% 80% at 85% 0%, rgba(255,255,255,0.14), transparent 60%), radial-gradient(50% 70% at 10% 100%, rgba(255,255,255,0.08), transparent 60%)',
          }}
        />
        <div className="stripe absolute inset-x-0 top-0 h-1.5" />
        <div className="container-page relative py-14 sm:py-16">
          <span className="eyebrow text-volt">
            <IconTrophy width={16} height={16} /> Лидерборд
          </span>
          <h1 className="mt-3 font-display text-4xl leading-tight sm:text-5xl">
            Рейтинг сообщества
          </h1>
          <p className="mt-3 max-w-xl text-paper/65">{VIEW_SUBTITLE[view]}</p>

          <div className="mt-7 flex flex-wrap gap-3">
            <div className="inline-flex rounded-full border border-paper/15 bg-paper/[0.06] p-1 text-sm font-semibold">
              {VIEWS.map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setView(key)}
                  className={`rounded-full px-4 py-1.5 transition ${
                    view === key ? 'bg-volt text-ink' : 'text-paper/70 hover:text-paper'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {view !== 'streak' && (
              <div className="inline-flex rounded-full border border-paper/15 bg-paper/[0.06] p-1 text-sm font-semibold">
                {PERIODS.map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setPeriod(key)}
                    className={`rounded-full px-4 py-1.5 transition ${
                      period === key ? 'bg-volt text-ink' : 'text-paper/70 hover:text-paper'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      <section className="container-page py-12 sm:py-16">
        {loading ? (
          <PageLoader />
        ) : error ? (
          <StatePanel
            tone="error"
            title="Не удалось загрузить рейтинг"
            description={error}
            action={
              <button onClick={reload} className="btn-ink">
                Повторить
              </button>
            }
          />
        ) : entries.length === 0 ? (
          <StatePanel
            title="Пока пусто"
            description="Как только появятся подтверждённые результаты, здесь выстроится таблица лидеров."
            icon={<IconTrophy />}
          />
        ) : (
          <>
            {podium.length > 0 && <Podium entries={podium} />}

            {rest.length > 0 && (
              <div className="mt-10 overflow-hidden rounded-xl2 border border-ink/[0.08] bg-white shadow-card">
                <div
                  className={`grid grid-cols-[3rem_1fr_auto] gap-3 border-b border-ink/10 bg-paper-soft/60 px-4 py-3 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-ink-600 ${hasSecondary ? 'sm:grid-cols-[3.5rem_1fr_7rem_5rem]' : 'sm:grid-cols-[3.5rem_1fr_5rem]'}`}
                >
                  <span>#</span>
                  <span>Бегун</span>
                  {hasSecondary && <span className="hidden text-right sm:block">Финишей</span>}
                  <span className="text-right">Значение</span>
                </div>
                <ul className="divide-y divide-ink/[0.06]">
                  {rest.map((e) => (
                    <li
                      key={e.user_id}
                      className={`grid grid-cols-[3rem_1fr_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-signal-wash/30 ${hasSecondary ? 'sm:grid-cols-[3.5rem_1fr_7rem_5rem]' : 'sm:grid-cols-[3.5rem_1fr_5rem]'}`}
                    >
                      <span className="font-display text-lg tabular text-ink-600">{e.rank}</span>
                      <Link
                        to={`/users/${e.user_id}`}
                        className="flex min-w-0 items-center gap-3 hover:text-signal"
                      >
                        <Avatar first={e.first_name} last={e.last_name} src={e.avatar_url} size="sm" />
                        <span className="min-w-0">
                          <span className="block truncate font-semibold text-ink">
                            {fullName(e.first_name, e.last_name)}
                          </span>
                          {e.city && (
                            <span className="block truncate font-mono text-[0.65rem] text-clay">
                              {e.city}
                            </span>
                          )}
                        </span>
                      </Link>
                      {hasSecondary && (
                        <span className="hidden text-right font-mono text-sm tabular text-ink-600 sm:block">
                          {e.secondary?.value ?? '—'}
                        </span>
                      )}
                      <span className="text-right font-display text-lg tabular text-signal">
                        {formatValue(e.value)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="mt-6 text-center font-mono text-xs text-clay">
              {entries.length} {plural(entries.length, 'участник', 'участника', 'участников')} в
              списке
            </p>
          </>
        )}
      </section>
    </div>
  )
}

function Podium({ entries }: { entries: DisplayEntry[] }) {
  // order for visual podium: 2nd, 1st, 3rd
  const order = [entries[1], entries[0], entries[2]].filter(Boolean)
  const heights = ['sm:mt-8', '', 'sm:mt-14']
  // Rank communicated by value, not hue: 1st = ink black, 2nd/3rd = a step lighter each.
  const rings = ['ring-[#B4B4AF]', 'ring-ink', 'ring-[#D6D6D2]']
  const badges = ['bg-[#B4B4AF]', 'bg-ink', 'bg-[#D6D6D2]']
  const badgeText = ['text-ink', 'text-paper', 'text-ink']

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {order.map((e, i) => {
        const rank = e.rank
        return (
          <Link
            to={`/users/${e.user_id}`}
            key={e.user_id}
            className={`group relative flex flex-col items-center rounded-xl2 border border-ink/[0.08] bg-white p-6 text-center shadow-card transition-all hover:-translate-y-1 hover:shadow-lift ${heights[i]}`}
          >
            <span
              className={`absolute -top-3 grid h-8 w-8 place-items-center rounded-full font-display text-sm ${badges[i]} ${badgeText[i]}`}
            >
              {rank}
            </span>
            <Avatar
              first={e.first_name}
              last={e.last_name}
              src={e.avatar_url}
              size="lg"
              className={`ring-2 ${rings[i]}`}
            />
            <h3 className="mt-3 font-display text-lg leading-tight text-ink group-hover:text-signal">
              {fullName(e.first_name, e.last_name)}
            </h3>
            {e.city && <p className="font-mono text-xs text-clay">{e.city}</p>}
            <div className="mt-4 flex items-baseline gap-1">
              <span className="font-display text-3xl tabular text-signal">
                {formatValue(e.value)}
              </span>
              <span className="font-mono text-xs text-clay">{e.valueLabel}</span>
            </div>
            {e.secondary && (
              <span className="mt-1 font-mono text-[0.65rem] uppercase tracking-wide text-ink-600">
                {e.secondary.value} {e.secondary.label}
              </span>
            )}
          </Link>
        )
      })}
    </div>
  )
}
