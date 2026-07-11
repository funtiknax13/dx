import { Link, useParams } from 'react-router-dom'
import { usersApi } from '../api/users'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../lib/useAsync'
import { fullName, plural } from '../lib/format'
import { Avatar } from '../components/ui/Avatar'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { ParticipationHistory } from '../components/ParticipationHistory'
import { IconArrow, IconTrophy, IconUser } from '../components/ui/icons'

export function PublicProfilePage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const { data, loading, error, reload } = useAsync(() => usersApi.publicProfile(id!), [id])

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

  const finishedCount = data.finished_count ?? data.history.filter((h) => h.finish_status === 'finished').length

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
                Профиль бегуна
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
              <div className="font-display text-4xl tabular text-volt">{data.rating}</div>
              <div className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-paper/55">
                рейтинг
              </div>
            </div>
            <div className="rounded-xl2 border border-paper/10 bg-paper/[0.05] px-6 py-4 text-center">
              <div className="font-display text-4xl tabular text-paper">{finishedCount}</div>
              <div className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.14em] text-paper/55">
                финишей
              </div>
            </div>
          </div>
        </div>
      </div>

      <section className="mt-10">
        <div className="mb-5 flex items-center gap-2">
          <IconTrophy className="text-signal" width={22} height={22} />
          <h2 className="font-display text-2xl sm:text-3xl">История участий</h2>
          <span className="ml-auto font-mono text-xs text-clay">
            {data.history.length} {plural(data.history.length, 'запись', 'записи', 'записей')}
          </span>
        </div>
        <ParticipationHistory
          history={data.history}
          editable={Boolean(isSelf)}
          onResultSubmitted={reload}
        />
      </section>
    </div>
  )
}
