import { useState } from 'react'
import { contestsApi } from '../api/contests'
import { useAsync } from '../lib/useAsync'
import { plural } from '../lib/format'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconTrophy } from '../components/ui/icons'
import { ContestCard } from '../components/ContestCard'

type Tab = 'upcoming' | 'past' | 'all'

export function ContestsListPage() {
  const { data, loading, error, reload } = useAsync(() => contestsApi.list(), [])
  const [tab, setTab] = useState<Tab>('upcoming')
  const activeCount = data?.filter((c) => c.phase !== 'voting_closed').length ?? 0
  const pastCount = data?.filter((c) => c.phase === 'voting_closed').length ?? 0
  const visible = (data ?? []).filter((c) =>
    tab === 'upcoming' ? c.phase !== 'voting_closed' : tab === 'past' ? c.phase === 'voting_closed' : true,
  )

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
          <>
            <div className="mb-8 inline-flex rounded-full border border-ink/10 bg-white p-1 text-sm font-semibold">
              {(
                [
                  ['upcoming', `Запланировано ${activeCount ? `· ${activeCount}` : ''}`],
                  ['past', `Прошедшие ${pastCount ? `· ${pastCount}` : ''}`],
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
            {visible.length === 0 ? (
              <StatePanel
                title={tab === 'past' ? 'Прошедших конкурсов пока нет' : 'Запланированных конкурсов нет'}
                icon={<IconTrophy />}
              />
            ) : (
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {visible.map((c, i) => (
                  <ContestCard key={c.id} contest={c} index={i} />
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
