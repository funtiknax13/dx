import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ratingApi } from '../api/rating'
import { leaderboardApi } from '../api/leaderboard'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../lib/useAsync'
import { fullName } from '../lib/format'
import { Avatar } from '../components/ui/Avatar'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconTrophy } from '../components/ui/icons'
import type { RatingPeriod, StatsLockReason } from '../types'

const FIELD_LABELS: Record<string, string> = {
  birthday: 'дата рождения',
  avatar: 'фото на аватар',
  city: 'город',
  gender: 'пол',
  phone: 'телефон',
  running_club: 'беговой клуб',
  prior_experience: 'бегали ли вы раньше с ДАЙ ХАРD',
  email_verified: 'подтверждение почты',
}

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
  const { user: authUser } = useAuth()
  const [view, setView] = useState<View>('rating')
  const [period, setPeriod] = useState<RatingPeriod>('all')

  const { data, loading, error, reload } = useAsync(async () => {
    if (view === 'rating') {
      const { entries, me, lockReason, missingFields } = await ratingApi.list(period)
      const toDisplay = (e: (typeof entries)[number]): DisplayEntry => ({
        rank: e.rank,
        user_id: e.user_id,
        first_name: e.first_name,
        last_name: e.last_name,
        avatar_url: e.avatar_url,
        city: e.city,
        value: e.score,
        valueLabel: 'балл',
        secondary: { value: e.finished_count, label: 'финишей' },
      })
      return {
        entries: entries.map(toDisplay),
        me: me ? toDisplay(me) : null,
        lockReason,
        missingFields,
      }
    }
    // Streak is period-agnostic — always fetched as "all" regardless of the
    // period toggle (which is hidden for this view anyway).
    const { entries, me, lockReason, missingFields } = await leaderboardApi.list(
      view,
      view === 'streak' ? 'all' : period,
    )
    const toDisplay = (e: (typeof entries)[number]): DisplayEntry => ({
      rank: e.rank,
      user_id: e.user_id,
      first_name: e.first_name,
      last_name: e.last_name,
      avatar_url: e.avatar_url,
      value: e.value,
      valueLabel: view === 'streak' ? 'DX подряд' : 'км',
    })
    return {
      entries: entries.map(toDisplay),
      me: me ? toDisplay(me) : null,
      lockReason,
      missingFields,
    }
  }, [view, period])

  const entries = data?.entries ?? []
  const meEntry = data?.me ?? null
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
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="eyebrow text-volt">
              <IconTrophy width={16} height={16} /> Лидерборд
            </span>
            <span className="chip border border-paper/15 bg-paper/[0.06] text-paper/60">
              Топ-20
            </span>
          </div>
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
        ) : data?.lockReason ? (
          <LockedStats lockReason={data.lockReason} missingFields={data.missingFields} />
        ) : entries.length === 0 ? (
          <StatePanel
            title="Пока пусто"
            description="Как только появятся подтверждённые результаты, здесь выстроится таблица лидеров."
            icon={<IconTrophy />}
          />
        ) : (
          <>
            {podium.length > 0 && <Podium entries={podium} myId={authUser?.id} />}

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
                    <RatingRow key={e.user_id} entry={e} hasSecondary={hasSecondary} isMe={e.user_id === authUser?.id} />
                  ))}
                </ul>
              </div>
            )}

            {meEntry && (
              <div className="mt-4 overflow-hidden rounded-xl2 border border-signal/30 bg-signal-wash shadow-card">
                <div className="border-b border-signal/20 px-4 py-2 font-mono text-[0.6rem] uppercase tracking-[0.14em] text-signal-600">
                  Ваш результат
                </div>
                <ul>
                  <RatingRow entry={meEntry} hasSecondary={hasSecondary} isMe />
                </ul>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}

function RatingRow({
  entry: e,
  hasSecondary,
  isMe,
}: {
  entry: DisplayEntry
  hasSecondary: boolean
  isMe: boolean
}) {
  return (
    <li
      className={`grid grid-cols-[3rem_1fr_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-signal-wash/30 ${hasSecondary ? 'sm:grid-cols-[3.5rem_1fr_7rem_5rem]' : 'sm:grid-cols-[3.5rem_1fr_5rem]'} ${isMe ? 'bg-signal-wash/50' : ''}`}
    >
      <span className="font-display text-lg tabular text-ink-600">{e.rank}</span>
      <Link to={`/users/${e.user_id}`} className="flex min-w-0 items-center gap-3 hover:text-signal">
        <Avatar first={e.first_name} last={e.last_name} src={e.avatar_url} size="sm" />
        <span className="min-w-0">
          <span className="flex items-center gap-1.5 truncate font-semibold text-ink">
            {fullName(e.first_name, e.last_name)}
            {isMe && (
              <span className="chip shrink-0 bg-signal px-1.5 py-0.5 text-white">
                Вы
              </span>
            )}
          </span>
          {e.city && (
            <span className="block truncate font-mono text-[0.65rem] text-clay">{e.city}</span>
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
  )
}

function Podium({ entries, myId }: { entries: DisplayEntry[]; myId?: number }) {
  // DOM order stays rank order (1st, 2nd, 3rd) — reads naturally top-to-bottom
  // on mobile (single column) and for screen readers. The "2nd, 1st, 3rd"
  // podium layout is a purely visual rearrangement, applied only at sm: and
  // up via CSS order, so it never affects the underlying document order.
  const order = ['sm:order-2', 'sm:order-1', 'sm:order-3']
  const heights = ['', 'sm:mt-8', 'sm:mt-14']
  // Rank communicated by value, not hue: 1st = ink black, 2nd/3rd = a step lighter each.
  const rings = ['ring-ink', 'ring-[#B4B4AF]', 'ring-[#D6D6D2]']
  const badges = ['bg-ink', 'bg-[#B4B4AF]', 'bg-[#D6D6D2]']
  const badgeText = ['text-paper', 'text-ink', 'text-ink']

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {entries.map((e, i) => {
        const rank = e.rank
        const isMe = e.user_id === myId
        return (
          <Link
            to={`/users/${e.user_id}`}
            key={e.user_id}
            className={`group relative flex flex-col items-center rounded-xl2 border p-6 text-center shadow-card transition-all hover:-translate-y-1 hover:shadow-lift ${order[i]} ${heights[i]} ${isMe ? 'border-signal bg-signal-wash' : 'border-ink/[0.08] bg-white'}`}
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
            <h3 className="mt-3 flex items-center gap-1.5 font-display text-lg leading-tight text-ink group-hover:text-signal">
              {fullName(e.first_name, e.last_name)}
              {isMe && (
                <span className="chip bg-signal px-1.5 py-0.5 text-white">
                  Вы
                </span>
              )}
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

function LockedStats({
  lockReason,
  missingFields,
}: {
  lockReason: Exclude<StatsLockReason, null>
  missingFields: string[]
}) {
  return (
    <div className="relative">
      <div aria-hidden className="pointer-events-none select-none blur-sm">
        <div className="grid gap-4 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-48 rounded-xl2 border border-ink/[0.08] bg-white" />
          ))}
        </div>
        <div className="mt-10 space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 rounded-xl2 border border-ink/[0.08] bg-white" />
          ))}
        </div>
      </div>
      <div className="absolute inset-0 flex items-center justify-center p-6">
        <div className="max-w-sm rounded-xl2 border border-ink/10 bg-white/95 p-6 text-center shadow-lift backdrop-blur">
          <IconTrophy className="mx-auto text-signal" width={28} height={28} />
          {lockReason === 'anonymous' ? (
            <>
              <h3 className="mt-3 font-display text-lg text-ink">Рейтинг — только для сообщества</h3>
              <p className="mt-2 text-sm text-ink-600">
                Зарегистрируйтесь и заполните профиль на 100%, чтобы увидеть рейтинг и статистику
                участников.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <Link to="/register" className="btn-primary btn-sm">
                  Зарегистрироваться
                </Link>
                <Link to="/login" className="btn-ghost btn-sm">
                  Войти
                </Link>
              </div>
            </>
          ) : (
            <>
              <h3 className="mt-3 font-display text-lg text-ink">Заполните профиль на 100%</h3>
              <p className="mt-2 text-sm text-ink-600">
                {missingFields.length > 0 ? (
                  <>
                    Осталось:{' '}
                    <span className="font-semibold text-signal-600">
                      {missingFields.map((f) => FIELD_LABELS[f] ?? f).join(', ')}
                    </span>
                    .
                  </>
                ) : (
                  'Загляните в профиль, чтобы завершить заполнение.'
                )}
              </p>
              <Link to="/profile" className="btn-primary btn-sm mt-4 inline-flex">
                Заполнить профиль
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
