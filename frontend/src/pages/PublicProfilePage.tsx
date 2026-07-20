import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { usersApi } from '../api/users'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../lib/useAsync'
import { formatDate, formatDistance, fullName, plural } from '../lib/format'
import { ACHIEVEMENT_BADGE_IMAGES } from '../lib/achievementBadges'
import { Avatar } from '../components/ui/Avatar'
import { PageLoader, Spinner } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { Pager } from '../components/ui/Pager'
import { ParticipationHistory } from '../components/ParticipationHistory'
import {
  IconArrow,
  IconCalendar,
  IconFlag,
  IconRoute,
  IconSpark,
  IconUser,
} from '../components/ui/icons'
import type { Achievement, PublicProfile } from '../types'

type Tab = 'history' | 'achievements'

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

export function PublicProfilePage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const { data, loading, error, reload } = useAsync(() => usersApi.publicProfile(id!), [id])
  const [tab, setTab] = useState<Tab>('history')
  const [historyPage, setHistoryPage] = useState(1)
  const history = useAsync(() => usersApi.historyPage(id!, historyPage), [id, historyPage])

  // Viewing own public profile — nudge to editable version
  const isSelf = user && String(user.id) === id

  if (loading) return <PageLoader />
  if (error || !data) {
    return (
      <div className="container-page py-16">
        <StatePanel
          tone="error"
          title="Профиль не найден"
          description={error ?? 'Пользователь не существует или профиль скрыт.'}
          icon={<IconUser />}
          action={
            <Link to="/rating" className="btn-ink">
              К рейтингу
            </Link>
          }
        />
      </div>
    )
  }

  const locked = data.lock_reason !== null
  const finishedCount = data.finished_count
  const historyTotalPages = Math.max(1, Math.ceil((history.data?.total ?? 0) / 20))

  return (
    <div className="container-page py-10 sm:py-14">
      {/* Public header — only name, avatar, rating, history (no private fields) */}
      <div className="relative overflow-hidden rounded-xl2 bg-ink p-6 text-paper shadow-lift sm:p-10">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            backgroundImage:
              'radial-gradient(50% 80% at 90% 0%, rgba(255,255,255,0.14), transparent 60%)',
          }}
        />
        <div className="stripe absolute inset-x-0 top-0 h-1.5" />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-5">
            <Avatar
              first={data.first_name}
              last={data.last_name}
              src={data.avatar_url}
              size="xl"
              className="ring-2 ring-paper/20"
            />
            <div>
              <span className="font-mono text-xs uppercase tracking-[0.2em] text-volt">
                {data.is_guest ? 'Гостевой профиль бегуна' : 'Профиль бегуна'}
              </span>
              <h1 className="mt-1 font-display text-3xl leading-tight sm:text-4xl">
                {fullName(data.first_name, data.last_name)}
              </h1>
              {isSelf && (
                <Link
                  to="/profile"
                  className="mt-2 inline-flex items-center gap-1.5 text-sm text-paper/70 hover:text-volt"
                >
                  Это вы — редактировать профиль <IconArrow width={14} height={14} />
                </Link>
              )}
            </div>
          </div>

          <div className="flex gap-4">
            <div className="rounded-xl2 border border-paper/10 bg-paper/[0.05] px-6 py-4 text-center">
              <div className="font-display text-4xl tabular text-volt">{locked ? '—' : data.rating}</div>
              <div className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-paper/55">
                рейтинг
              </div>
            </div>
            <div className="rounded-xl2 border border-paper/10 bg-paper/[0.05] px-6 py-4 text-center">
              <div className="font-display text-4xl tabular text-paper">{locked ? '—' : finishedCount}</div>
              <div className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-paper/55">
                финишей
              </div>
            </div>
          </div>
        </div>
      </div>

      {locked ? (
        <LockedProfileStats lockReason={data.lock_reason!} missingFields={data.missing_fields} />
      ) : (
        <StatsGrid data={data} />
      )}

      {/* Tabs — achievements are derived stats, gated same as the rest;
          history is the same kind of record a public race protocol already
          shows, so it stays visible either way. */}
      <div className="mt-10 flex gap-2 overflow-x-auto pb-1">
        {(
          [
            ['history', 'История участий'],
            ...(locked ? [] : [['achievements', 'Достижения']]),
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold transition ${
              tab === key ? 'bg-ink text-paper' : 'border border-ink/10 text-ink-600 hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'history' && (
        <section className="mt-6">
          <div className="mb-5 flex items-center justify-end gap-2">
            <span className="font-mono text-xs text-clay">
              {history.data?.total ?? 0}{' '}
              {plural(history.data?.total ?? 0, 'запись', 'записи', 'записей')}
            </span>
          </div>
          {history.loading ? (
            <div className="flex justify-center py-10">
              <Spinner className="text-signal" />
            </div>
          ) : (
            <>
              <ParticipationHistory
                history={history.data?.items ?? []}
                editable={Boolean(isSelf)}
                onResultSubmitted={() => {
                  history.reload()
                  reload()
                }}
              />
              <Pager page={historyPage} totalPages={historyTotalPages} onChange={setHistoryPage} />
            </>
          )}
        </section>
      )}

      {tab === 'achievements' && !locked && data.achievements && (
        <section className="mt-6">
          <div className="flex flex-wrap gap-4">
            {data.achievements.map((a) => (
              <AchievementBadge key={a.threshold} achievement={a} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function AchievementBadge({ achievement }: { achievement: Achievement }) {
  const { threshold, reached, reached_at, event_title } = achievement
  const image = ACHIEVEMENT_BADGE_IMAGES[threshold]
  return (
    <div
      className={`flex w-32 flex-col items-center gap-2 rounded-xl2 border p-4 text-center shadow-card ${
        reached ? 'border-ink/[0.08] bg-white' : 'border-dashed border-ink/15 bg-white/40'
      }`}
    >
      {image ? (
        <img
          src={image}
          alt={`Достижение: ${threshold} DX`}
          className={`h-24 w-auto shrink-0 ${reached ? '' : 'opacity-30 grayscale'}`}
        />
      ) : (
        <div
          className={`grid h-16 w-16 shrink-0 place-items-center rounded-full border-4 font-display text-2xl tabular ${
            reached ? 'border-signal text-ink' : 'border-ink/15 text-ink/30'
          }`}
        >
          {threshold}
        </div>
      )}
      {reached ? (
        <div className="min-w-0">
          {reached_at && (
            // Covered entirely by an admin-entered starting balance (see
            // RunnerBaseline) when absent — there's no specific run to
            // attribute it to, so just leave the date blank.
            <p className="font-mono text-[0.65rem] tabular text-ink-600">
              {formatDate(reached_at, { day: 'numeric', month: 'short', year: 'numeric' })}
            </p>
          )}
          {event_title && (
            <p className="mt-0.5 truncate font-mono text-[0.6rem] text-clay" title={event_title}>
              {event_title}
            </p>
          )}
        </div>
      ) : (
        <p className="font-mono text-[0.6rem] uppercase tracking-wide text-clay">Впереди</p>
      )}
    </div>
  )
}

function StatsGrid({ data }: { data: PublicProfile }) {
  const stats = [
    {
      icon: <IconCalendar width={18} height={18} />,
      label: 'Дата регистрации',
      value: formatDate(data.registered_at, { day: 'numeric', month: 'long', year: 'numeric' }),
    },
    {
      icon: <IconCalendar width={18} height={18} />,
      label: 'Первая пробежка',
      value: data.first_run_date
        ? formatDate(data.first_run_date, { day: 'numeric', month: 'long', year: 'numeric' })
        : '—',
    },
    {
      icon: <IconRoute width={18} height={18} />,
      label: 'Пробежек всего',
      value: String(data.total_runs_count ?? 0),
    },
    {
      icon: <IconFlag width={18} height={18} />,
      label: 'Км по полным DX',
      value: formatDistance(data.full_dx_km ?? 0),
    },
    {
      icon: <IconFlag width={18} height={18} />,
      label: 'Км за последний месяц',
      value: formatDistance(data.km_this_month ?? 0),
    },
    {
      icon: <IconSpark width={18} height={18} />,
      label: 'Текущая серия',
      value: `${data.current_streak ?? 0} DX подряд`,
    },
    {
      icon: <IconSpark width={18} height={18} />,
      label: 'Лучшая серия',
      value: `${data.longest_streak ?? 0} DX подряд`,
    },
  ]

  return (
    <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
      {stats.map((s) => (
        <div
          key={s.label}
          className="rounded-xl2 border border-ink/[0.08] bg-white p-4 text-center shadow-card"
        >
          <div className="mx-auto mb-1 flex h-7 w-7 items-center justify-center text-signal">
            {s.icon}
          </div>
          <div className="font-display text-lg leading-tight tabular text-ink">{s.value}</div>
          <div className="mt-1 font-mono text-[0.6rem] uppercase tracking-[0.1em] text-clay">
            {s.label}
          </div>
        </div>
      ))}
    </div>
  )
}

function LockedProfileStats({
  lockReason,
  missingFields,
}: {
  lockReason: 'anonymous' | 'profile_incomplete'
  missingFields: string[]
}) {
  return (
    <div className="mt-6 rounded-xl2 border border-ink/[0.08] bg-white p-6 text-center shadow-card sm:p-8">
      {lockReason === 'anonymous' ? (
        <>
          <p className="text-sm text-ink-600">
            Зарегистрируйтесь и заполните профиль на 100%, чтобы видеть статистику участников
            сообщества.
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
          <p className="text-sm text-ink-600">
            Заполните профиль на 100%, чтобы видеть статистику других участников.
            {missingFields.length > 0 && (
              <>
                {' '}
                Осталось:{' '}
                <span className="font-semibold text-signal-600">
                  {missingFields.map((f) => FIELD_LABELS[f] ?? f).join(', ')}
                </span>
                .
              </>
            )}
          </p>
          <Link to="/profile" className="btn-primary btn-sm mt-4 inline-flex">
            Заполнить профиль
          </Link>
        </>
      )}
    </div>
  )
}
