import { Link, useParams } from 'react-router-dom'
import { eventsApi } from '../api/events'
import { media } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { formatDate, isPast, plural } from '../lib/format'
import { GroupCard } from '../components/GroupCard'
import { PhotoGallery } from '../components/PhotoGallery'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconArrow, IconCalendar, IconPin } from '../components/ui/icons'
import type { EventDetail, EventPhoto, Group } from '../types'

export function EventDetailPage() {
  const { id } = useParams<{ id: string }>()

  const { data, loading, error, reload } = useAsync<{
    event: EventDetail
    groups: Group[]
    photos: EventPhoto[]
  }>(async () => {
    const event = await eventsApi.detail(id!)
    const groups = event.groups?.length
      ? event.groups
      : await eventsApi.groups(id!).catch(() => [])
    const photos = event.photos?.length
      ? event.photos
      : await eventsApi.photos(id!).catch(() => [])
    return { event, groups, photos }
  }, [id])

  if (loading) return <PageLoader />
  if (error || !data) {
    return (
      <div className="container-page py-16">
        <StatePanel
          tone="error"
          title="Событие не найдено"
          description={error ?? 'Проверьте ссылку или вернитесь к списку событий.'}
          action={
            <div className="flex gap-3">
              <button onClick={reload} className="btn-ghost">
                Повторить
              </button>
              <Link to="/events" className="btn-ink">
                К событиям
              </Link>
            </div>
          }
        />
      </div>
    )
  }

  const { event, groups, photos } = data
  const cover = media(event.cover_url)
  const past = isPast(event.date)

  return (
    <article>
      {/* Cover hero */}
      <header className="relative overflow-hidden bg-ink text-paper">
        {cover ? (
          <>
            <img
              src={cover}
              alt=""
              className="absolute inset-0 h-full w-full object-cover opacity-45"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-ink via-ink/70 to-ink/30" />
          </>
        ) : (
          <div
            className="absolute inset-0 opacity-70"
            style={{
              backgroundImage:
                'radial-gradient(60% 80% at 85% 10%, rgba(255,255,255,0.14), transparent 60%)',
            }}
          />
        )}
        <div className="container-page relative py-14 sm:py-20">
          <Link
            to="/events"
            className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em] text-paper/70 hover:text-volt"
          >
            <IconArrow width={14} height={14} className="rotate-180" /> Все события
          </Link>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <span className={`chip ${past ? 'bg-paper/15 text-paper' : 'bg-volt text-ink'}`}>
              {past ? 'Прошло' : 'Скоро'}
            </span>
            <span className="inline-flex items-center gap-1.5 font-mono text-sm text-paper/80">
              <IconCalendar width={16} height={16} className="text-volt" />
              {formatDate(event.date)}
            </span>
          </div>
          <h1 className="mt-4 max-w-3xl font-display text-4xl leading-[1.03] sm:text-5xl lg:text-6xl">
            {event.title}
          </h1>
          {event.location_summary && (
            <p className="mt-4 inline-flex items-center gap-2 text-paper/75">
              <IconPin width={18} height={18} className="text-volt" />
              {event.location_summary}
            </p>
          )}
          <div className="mt-6 flex flex-wrap gap-2 font-mono text-xs">
            <span className="chip bg-paper/10 text-paper">
              {groups.length} {plural(groups.length, 'группа', 'группы', 'групп')}
            </span>
            {typeof event.participant_count === 'number' && (
              <span className="chip bg-paper/10 text-paper">
                {event.participant_count}{' '}
                {plural(event.participant_count, 'участник', 'участника', 'участников')}
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="container-page grid gap-12 py-12 sm:py-16 lg:grid-cols-[1fr_340px]">
        {/* Main column */}
        <div className="order-2 lg:order-1">
          {event.description && (
            <section className="mb-12">
              <h2 className="eyebrow mb-3">
                <span className="h-1.5 w-1.5 rounded-full bg-signal" /> Описание
              </h2>
              <div className="whitespace-pre-line text-base leading-relaxed text-ink-700">
                {event.description}
              </div>
            </section>
          )}

          <section className="mb-12">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="font-display text-2xl sm:text-3xl">Группы</h2>
              <span className="font-mono text-xs text-clay">
                {groups.length} {plural(groups.length, 'группа', 'группы', 'групп')}
              </span>
            </div>
            {groups.length ? (
              <div className="grid gap-3">
                {groups.map((g, i) => (
                  <GroupCard key={g.id} group={g} index={i} />
                ))}
              </div>
            ) : (
              <StatePanel
                title="Групп пока нет"
                description="Организатор ещё не добавил группы к этому событию."
              />
            )}
          </section>

          {photos.length > 0 && (
            <section>
              <div className="mb-5 flex items-center justify-between">
                <h2 className="font-display text-2xl sm:text-3xl">Фотогалерея</h2>
                <span className="font-mono text-xs text-clay">{photos.length} фото</span>
              </div>
              <PhotoGallery photos={photos} />
            </section>
          )}
        </div>

        {/* Sidebar */}
        <aside className="order-1 lg:order-2">
          <div className="sticky top-24 space-y-4">
            <div className="card-ink p-6">
              <h3 className="font-mono text-xs uppercase tracking-[0.2em] text-volt">Событие</h3>
              <dl className="mt-4 space-y-3 text-sm">
                <div className="flex items-center justify-between gap-4 border-b border-paper/10 pb-3">
                  <dt className="text-paper/55">Дата</dt>
                  <dd className="font-mono tabular">{formatDate(event.date)}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-paper/10 pb-3">
                  <dt className="text-paper/55">Групп</dt>
                  <dd className="font-mono tabular">{groups.length}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-paper/55">Статус</dt>
                  <dd className="font-mono">{past ? 'завершено' : 'предстоит'}</dd>
                </div>
              </dl>
              {groups[0] && (
                <Link to={`/groups/${groups[0].id}`} className="btn-volt mt-6 w-full">
                  Открыть первую группу
                </Link>
              )}
            </div>
          </div>
        </aside>
      </div>
    </article>
  )
}
