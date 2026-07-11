import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { groupsApi } from '../api/groups'
import { signupsApi } from '../api/signups'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../lib/useAsync'
import { formatDistance, formatTime, paceRange, plural } from '../lib/format'
import { ProtocolTable } from '../components/ProtocolTable'
import { RouteMap } from '../components/RouteMap'
import { ElevationProfile } from '../components/ElevationProfile'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { Spinner } from '../components/ui/Spinner'
import {
  IconArrow,
  IconCheck,
  IconClock,
  IconDownload,
  IconFlag,
  IconPin,
  IconRoute,
} from '../components/ui/icons'
import type { Group, GroupSignupState, Protocol, RouteMap as RouteMapData } from '../types'

export function GroupDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { isAuthenticated } = useAuth()

  const { data, loading, error, reload } = useAsync<{
    group: Group
    protocol: Protocol | null
    route: RouteMapData | null
  }>(async () => {
    const [group, protocol, route] = await Promise.all([
      groupsApi.detail(id!),
      groupsApi.protocol(id!).catch(() => null),
      groupsApi.routeMap(id!).catch(() => null),
    ])
    return { group, protocol, route }
  }, [id])

  if (loading) return <PageLoader />
  if (error || !data) {
    return (
      <div className="container-page py-16">
        <StatePanel
          tone="error"
          title="Группа не найдена"
          description={error ?? 'Проверьте ссылку.'}
          action={
            <Link to="/events" className="btn-ink">
              К событиям
            </Link>
          }
        />
      </div>
    )
  }

  const { group, protocol, route } = data
  const pace = paceRange(group.pace_min, group.pace_max)
  const hasRoute = Boolean(route && route.points.length)

  return (
    <div>
      {/* Header */}
      <header className="border-b border-ink/10 bg-paper-soft/50">
        <div className="container-page py-10 sm:py-12">
          <Link
            to={`/events/${group.event_id}`}
            className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em] text-ink-600 hover:text-signal"
          >
            <IconArrow width={14} height={14} className="rotate-180" /> К событию
          </Link>

          <div className="mt-5 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex items-start gap-4">
              {group.distance_code && (
                <span className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-ink font-display text-2xl text-volt">
                  {group.distance_code}
                </span>
              )}
              <div>
                <h1 className="font-display text-3xl leading-tight sm:text-4xl">{group.name}</h1>
                <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-600">
                  {group.location && (
                    <span className="inline-flex items-center gap-1.5">
                      <IconPin width={16} height={16} className="text-signal" />
                      {group.location}
                    </span>
                  )}
                  {pace && (
                    <span className="inline-flex items-center gap-1.5 font-mono tabular">
                      <IconRoute width={16} height={16} className="text-signal" />
                      {pace} /км
                    </span>
                  )}
                  {group.target_distance_km != null && (
                    <span className="inline-flex items-center gap-1.5 font-mono tabular">
                      <IconFlag width={16} height={16} className="text-signal" />
                      {formatDistance(group.target_distance_km)}
                    </span>
                  )}
                  {group.start_time && (
                    <span className="inline-flex items-center gap-1.5 font-mono tabular">
                      <IconClock width={16} height={16} className="text-signal" />
                      старт {formatTime(group.start_time)}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <SignupControl groupId={group.id} authenticated={isAuthenticated} onChange={reload} />
          </div>
        </div>
      </header>

      <div className="container-page grid gap-10 py-12 lg:grid-cols-[1fr_minmax(320px,380px)]">
        {/* Protocol — primary */}
        <section className="order-2 lg:order-1">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="font-display text-2xl sm:text-3xl">Протокол забега</h2>
            {protocol && (
              <span className="font-mono text-xs text-clay">
                {protocol.finishers.length}{' '}
                {plural(protocol.finishers.length, 'финишёр', 'финишёра', 'финишёров')}
                {protocol.dnf.length > 0 && ` · ${protocol.dnf.length} DNF`}
              </span>
            )}
          </div>
          {protocol ? (
            <ProtocolTable protocol={protocol} />
          ) : (
            <StatePanel
              title="Протокол недоступен"
              description="Результаты появятся после импорта списка участников администратором."
              icon={<IconFlag />}
            />
          )}
        </section>

        {/* Route sidebar */}
        <aside className="order-1 space-y-5 lg:order-2">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl">Маршрут</h2>
            {hasRoute && (
              <a
                href={groupsApi.routeGpxUrl(group.id)}
                className="btn-ink btn-sm"
                download
                target="_blank"
                rel="noreferrer"
              >
                <IconDownload width={16} height={16} /> GPX
              </a>
            )}
          </div>

          {hasRoute && route ? (
            <>
              <RouteMap points={route.points} className="h-[320px]" />
              {route.distance_km != null && (
                <div className="grid grid-cols-3 gap-2">
                  <MiniStat label="Дистанция" value={`${route.distance_km.toFixed(1)} км`} />
                  <MiniStat label="Набор" value={`${Math.round(route.ascent_m ?? 0)} м`} />
                  <MiniStat label="Спуск" value={`${Math.round(route.descent_m ?? 0)} м`} />
                </div>
              )}
              {route.elevation?.length > 1 && (
                <ElevationProfile
                  data={route.elevation}
                  ascent={route.ascent_m}
                  descent={route.descent_m}
                />
              )}
            </>
          ) : (
            <div className="rounded-xl2 border border-dashed border-ink/15 bg-white/50 px-5 py-10 text-center">
              <IconRoute className="mx-auto mb-3 text-clay" width={28} height={28} />
              <p className="font-display text-lg text-ink">Маршрут не загружен</p>
              <p className="mt-1 text-sm text-ink-600">
                Организатор ещё не прикрепил GPX-трек к этой группе.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-ink/[0.08] bg-white p-3 text-center shadow-card">
      <div className="font-display text-lg tabular text-ink">{value}</div>
      <div className="mt-0.5 font-mono text-[0.6rem] uppercase tracking-[0.12em] text-clay">
        {label}
      </div>
    </div>
  )
}

function SignupControl({
  groupId,
  authenticated,
  onChange,
}: {
  groupId: number
  authenticated: boolean
  onChange: () => void
}) {
  const navigate = useNavigate()
  const [state, setState] = useState<GroupSignupState | null>(null)
  const [loading, setLoading] = useState(authenticated)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!authenticated) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const s = await groupsApi.signupState(groupId)
      setState(s)
    } catch {
      setState({ signed_up: false })
    } finally {
      setLoading(false)
    }
  }, [authenticated, groupId])

  useEffect(() => {
    void load()
  }, [load])

  if (!authenticated) {
    return (
      <div className="shrink-0">
        <button onClick={() => navigate('/login')} className="btn-primary btn-lg w-full sm:w-auto">
          Войдите, чтобы записаться
        </button>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="btn-ghost btn-lg pointer-events-none w-full justify-center sm:w-auto">
        <Spinner className="h-5 w-5" />
      </div>
    )
  }

  const signedUp = state?.signed_up

  const toggle = async () => {
    setBusy(true)
    setMsg(null)
    try {
      if (signedUp && state?.signup_id) {
        await signupsApi.remove(state.signup_id)
        setState({ signed_up: false })
      } else {
        const created = await signupsApi.create(groupId)
        setState({ signed_up: true, signup_id: created.id })
      }
      onChange()
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : 'Не удалось обновить запись')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="shrink-0">
      <button
        onClick={toggle}
        disabled={busy}
        className={`btn-lg w-full justify-center sm:w-auto ${signedUp ? 'btn-ghost' : 'btn-primary'}`}
      >
        {busy ? (
          <Spinner className="h-5 w-5" />
        ) : signedUp ? (
          <>
            <IconCheck width={18} height={18} /> Вы записаны · отменить
          </>
        ) : (
          <>Записаться в группу</>
        )}
      </button>
      {msg && <p className="mt-2 text-right text-xs text-signal-600">{msg}</p>}
    </div>
  )
}
