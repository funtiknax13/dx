import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { eventsApi } from '../api/events'
import { media } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { asList } from '../lib/list'
import { formatDate, isPast } from '../lib/format'
import { EventCard } from '../components/EventCard'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconArrow, IconCalendar, IconPin, IconRunner, IconSpark } from '../components/ui/icons'
import type { EventSummary } from '../types'

type Tab = 'upcoming' | 'past' | 'all'

export function EventsPage() {
  const { data, loading, error, reload } = useAsync(() => eventsApi.list(), [])
  const [tab, setTab] = useState<Tab>('upcoming')

  const events = useMemo(() => asList<EventSummary>(data), [data])
  const upcoming = useMemo(
    () => events.filter((e) => !isPast(e.date)).sort((a, b) => a.date.localeCompare(b.date)),
    [events],
  )
  const past = events.filter((e) => isPast(e.date))
  const nextEvent = upcoming[0] ?? null
  const shown = tab === 'upcoming' ? upcoming : tab === 'past' ? past : events

  return (
    <div>
      <Hero nextEvent={nextEvent} upcomingCount={upcoming.length} totalCount={events.length} />

      <section id="events" className="container-page py-12 sm:py-16">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <span className="eyebrow">
              <span className="h-1.5 w-1.5 rounded-full bg-signal" /> Календарь
            </span>
            <h2 className="mt-2 font-display text-3xl sm:text-4xl">События сообщества</h2>
          </div>
          <div className="inline-flex rounded-full border border-ink/10 bg-white p-1 text-sm font-semibold">
            {(
              [
                ['upcoming', `Ближайшие ${upcoming.length ? `· ${upcoming.length}` : ''}`],
                ['past', 'Прошедшие'],
                ['all', 'Все'],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`rounded-full px-4 py-1.5 transition ${
                  tab === key ? 'bg-ink text-paper' : 'text-ink-600 hover:text-ink'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <PageLoader />
        ) : error ? (
          <StatePanel
            tone="error"
            title="Не удалось загрузить события"
            description={error}
            icon={<IconRunner />}
            action={
              <button onClick={reload} className="btn-ink">
                Повторить
              </button>
            }
          />
        ) : shown.length === 0 ? (
          <StatePanel
            title={tab === 'upcoming' ? 'Пока нет запланированных событий' : 'Здесь пусто'}
            description="Загляните позже — организаторы регулярно добавляют новые старты и тренировки."
            icon={<IconSpark />}
          />
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((event, i) => (
              <EventCard key={event.id} event={event} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function Hero({
  nextEvent,
  upcomingCount,
  totalCount,
}: {
  nextEvent: EventSummary | null
  upcomingCount: number
  totalCount: number
}) {
  return (
    <section className="relative overflow-hidden bg-ink text-paper">
      {/* atmospheric background — pure value, no hue */}
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          backgroundImage:
            'radial-gradient(60% 80% at 85% 10%, rgba(255,255,255,0.12), transparent 60%), radial-gradient(50% 60% at 5% 90%, rgba(255,255,255,0.06), transparent 60%)',
        }}
      />
      <div className="stripe absolute inset-x-0 top-0 h-1.5" />
      <div className="container-page relative grid gap-10 py-16 sm:py-20 lg:grid-cols-[1.1fr_1fr] lg:items-center">
        <div className="animate-fade-up">
          <span className="eyebrow text-volt">
            <span className="h-1.5 w-1.5 rounded-full bg-volt" /> DАЙ ХАРD · Чебоксары ·
            #diehardcheb
          </span>
          <h1 className="mt-4 font-display text-4xl leading-[1.02] sm:text-5xl lg:text-6xl">
            Длительные пробежки
            <br />
            каждое <span className="bg-paper px-2 text-ink">воскресенье</span>.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-paper/70">
            🏃 Беговое сообщество Чебоксар без формальностей и вступительных взносов — приходи,
            беги в своём темпе и следи за прогрессом. Группы под любой уровень, маршруты, протоколы
            забегов и рейтинг активности.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {nextEvent ? (
              <Link to={`/events/${nextEvent.id}`} className="btn-volt btn-lg">
                Записаться на ближайшую тренировку
              </Link>
            ) : (
              <a href="#events" className="btn-volt btn-lg">
                Смотреть события
              </a>
            )}
            <a
              href="/rating"
              className="btn btn-lg border border-paper/25 bg-transparent text-paper hover:border-paper/50 hover:bg-paper/[0.06]"
            >
              Рейтинг бегунов
            </a>
          </div>
          <div className="mt-10 flex gap-8 font-mono text-xs text-paper/50">
            <span>
              <span className="tabular text-paper">{upcomingCount}</span> ближайших
            </span>
            <span>
              <span className="tabular text-paper">{totalCount}</span> всего в календаре
            </span>
          </div>
        </div>

        <div className="animate-fade-up" style={{ animationDelay: '120ms' }}>
          {nextEvent ? <NextEventCard event={nextEvent} /> : <HowItWorksCard />}
        </div>
      </div>
    </section>
  )
}

function NextEventCard({ event }: { event: EventSummary }) {
  const cover = media(event.cover_url)
  return (
    <Link
      to={`/events/${event.id}`}
      className="group relative block overflow-hidden rounded-xl2 border border-paper/10 shadow-lift transition-transform hover:-translate-y-1"
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-paper/10">
        {cover ? (
          <img
            src={cover}
            alt={event.title}
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <IconRunner width={56} height={56} className="text-paper/25" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-ink via-ink/50 to-transparent" />
      </div>
      <div className="absolute inset-x-0 bottom-0 p-5">
        <span className="chip bg-volt text-ink">Ближайшая тренировка</span>
        <h3 className="mt-3 font-display text-2xl leading-tight text-paper">{event.title}</h3>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-paper/75">
          <span className="inline-flex items-center gap-1.5">
            <IconCalendar width={15} height={15} className="text-volt" />
            {formatDate(event.date, { weekday: 'long', day: 'numeric', month: 'long' })}
          </span>
          {event.location_summary && (
            <span className="inline-flex items-center gap-1.5">
              <IconPin width={15} height={15} className="text-volt" />
              {event.location_summary}
            </span>
          )}
        </div>
        <span className="mt-4 inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.16em] text-volt">
          Смотреть и записаться
          <IconArrow width={13} height={13} className="transition-transform group-hover:translate-x-1" />
        </span>
      </div>
    </Link>
  )
}

function HowItWorksCard() {
  return (
    <div className="rounded-xl2 border border-paper/10 bg-paper/[0.04] p-6">
      <div className="flex items-center gap-3 text-volt">
        <IconRunner width={22} height={22} />
        <span className="font-mono text-xs uppercase tracking-[0.2em]">Как это работает</span>
      </div>
      <ol className="mt-4 space-y-2 text-sm text-paper/75">
        <li className="flex gap-2">
          <span className="font-mono text-paper/50">01</span> Выбери событие и группу по темпу
        </li>
        <li className="flex gap-2">
          <span className="font-mono text-paper/50">02</span> Запишись и пробеги маршрут
        </li>
        <li className="flex gap-2">
          <span className="font-mono text-paper/50">03</span> Загрузи результат и войди в протокол
        </li>
      </ol>
    </div>
  )
}
