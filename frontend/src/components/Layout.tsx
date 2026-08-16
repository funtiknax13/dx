import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { adminToolsUrl } from '../api/client'
import { supportApi } from '../api/support'
import { staffApi } from '../api/staff'
import { surveysApi } from '../api/surveys'
import { Avatar } from './ui/Avatar'
import { MobileTabBar } from './MobileTabBar'
import { InstallAppButton } from './InstallAppButton'
import { IconClipboard, IconMail, IconMenu, IconSettings, IconX } from './ui/icons'
import { plural } from '../lib/format'
import logoMarkSquare from '../assets/brand/logo-mark-square.png'
import logoFullDark from '../assets/brand/logo-full-dark.png'
import logoFullLight from '../assets/brand/logo-full-light.png'

function isStaff(role?: string) {
  return role === 'organizer' || role === 'admin'
}

const NAV = [
  { to: '/events', label: 'События' },
  { to: '/rating', label: 'Рейтинг' },
]

/** Polls for unread staff replies while logged in — the "user sees if
 * they've received a support message" requirement. A simple interval
 * rather than websockets/SSE: support replies aren't latency-sensitive. */
function useUnreadSupportCount(isAuthenticated: boolean): number {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!isAuthenticated) {
      setCount(0)
      return
    }
    let active = true
    const check = () => {
      supportApi
        .unreadCount()
        .then((res) => {
          if (active) setCount(res.count)
        })
        .catch(() => {})
    }
    check()
    const interval = setInterval(check, 60_000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [isAuthenticated])

  return count
}

/** Whether the newbie survey is currently blocking this runner's stats — the
 * gate itself only ever surfaces on the rating/profile pages, so without
 * this a runner has no reason to go looking for it. Same polling pattern as
 * the other nav badges above. */
function useSurveyPending(isAuthenticated: boolean): boolean {
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!isAuthenticated) {
      setPending(false)
      return
    }
    let active = true
    const check = () => {
      surveysApi
        .active()
        .then((survey) => {
          if (active) setPending(Boolean(survey))
        })
        .catch(() => {})
    }
    check()
    const interval = setInterval(check, 60_000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [isAuthenticated])

  return pending
}

/** Polls the same "needs a look" counts admin-tools shows as nav badges —
 * tickets/claims/moderation — so staff notice from the main site without
 * having to open admin-tools first (they might not visit it every day). */
function useStaffAttentionCounts(isStaff: boolean): { total: number; tooltip: string } {
  const [counts, setCounts] = useState({ tickets: 0, claims: 0, moderation: 0 })

  useEffect(() => {
    if (!isStaff) {
      setCounts({ tickets: 0, claims: 0, moderation: 0 })
      return
    }
    let active = true
    const check = () => {
      staffApi
        .attentionCounts()
        .then((res) => {
          if (active) setCounts(res)
        })
        .catch(() => {})
    }
    check()
    const interval = setInterval(check, 60_000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [isStaff])

  const parts = [
    counts.tickets > 0 && `${counts.tickets} ${plural(counts.tickets, 'новый тикет', 'новых тикета', 'новых тикетов')}`,
    counts.claims > 0 && `${counts.claims} ${plural(counts.claims, 'заявка на объединение', 'заявки на объединение', 'заявок на объединение')}`,
    counts.moderation > 0 && `${counts.moderation} ${plural(counts.moderation, 'результат на модерации', 'результата на модерации', 'результатов на модерации')}`,
  ].filter(Boolean)

  return {
    total: counts.tickets + counts.claims + counts.moderation,
    tooltip: parts.length ? parts.join(' · ') : 'Ждёт внимания',
  }
}

/** Floating reminder that the newbie survey is waiting — fixed to the
 * viewport (not tucked inside the nav), so it's the same on mobile and
 * desktop without opening a menu first. Dismissible for the current
 * browsing session (Layout stays mounted across in-app navigation; a full
 * reload — or the survey still being pending next visit — brings it back). */
function SurveyReminder({ pending }: { pending: boolean }) {
  const [dismissed, setDismissed] = useState(false)
  if (!pending || dismissed) return null
  return (
    <div
      // Mobile keeps clear of the fixed bottom tab bar (h-16 + safe area);
      // desktop has no tab bar, so it sits low-right as before.
      className="fixed inset-x-4 z-50 animate-fade-up bottom-[calc(4.5rem+env(safe-area-inset-bottom))] sm:inset-x-auto sm:bottom-5 sm:right-5 sm:max-w-sm"
    >
      <div className="flex items-start gap-3 rounded-xl2 border border-ink/10 bg-white p-4 shadow-lift">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-danger-wash text-danger">
          <IconClipboard width={18} height={18} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">Есть анкета новичка</p>
          <p className="mt-0.5 text-xs text-ink-600">
            Заполните, чтобы открыть рейтинг и статистику сообщества.
          </p>
          <Link to="/survey" className="btn-primary btn-sm mt-3 inline-flex" onClick={() => setDismissed(true)}>
            Заполнить анкету
          </Link>
        </div>
        <button
          onClick={() => setDismissed(true)}
          aria-label="Скрыть"
          className="shrink-0 rounded-full p-1 text-clay transition hover:bg-ink/5 hover:text-ink"
        >
          <IconX width={14} height={14} />
        </button>
      </div>
    </div>
  )
}

function Brand({ onClick, light = false }: { onClick?: () => void; light?: boolean }) {
  return (
    <Link to="/events" onClick={onClick} className="group flex items-center gap-3">
      <img
        src={logoMarkSquare}
        alt=""
        className="h-9 w-9 shrink-0 rounded-lg transition-transform group-hover:-rotate-6"
      />
      <img
        src={light ? logoFullLight : logoFullDark}
        alt="DАЙ ХАРD Чебоксары"
        className="h-9 w-auto"
      />
    </Link>
  )
}

export function Layout() {
  const { user, isAuthenticated, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const unreadSupport = useUnreadSupportCount(isAuthenticated)
  const attention = useStaffAttentionCounts(isStaff(user?.role))
  const surveyPending = useSurveyPending(isAuthenticated)

  useEffect(() => setOpen(false), [location.pathname])

  const navItems =
    isAuthenticated && user
      ? [...NAV, { to: `/users/${user.id}`, label: 'Моя статистика' }]
      : NAV

  return (
    <div className="flex min-h-screen flex-col pb-[calc(4rem+env(safe-area-inset-bottom))] md:pb-0">
      <header className="sticky top-0 z-40 border-b border-ink/10 bg-paper/85 backdrop-blur-md">
        <div className="container-page flex h-16 items-center justify-between gap-4">
          <div className="flex items-center gap-8">
            <Brand />
            <nav className="hidden items-center gap-1 md:flex">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `rounded-full px-4 py-2 text-sm font-semibold transition ${
                      isActive
                        ? 'bg-ink text-paper'
                        : 'text-ink-600 hover:bg-ink/[0.05] hover:text-ink'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="hidden items-center gap-3 md:flex">
            <Link
              to="/support"
              title="Поддержка"
              aria-label="Поддержка"
              className="relative grid h-10 w-10 place-items-center rounded-full text-ink-600 transition hover:bg-ink/[0.05] hover:text-ink"
            >
              <IconMail width={18} height={18} />
              {unreadSupport > 0 && (
                <span className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-signal px-1 text-[10px] font-bold text-white">
                  {unreadSupport}
                </span>
              )}
            </Link>
            {isAuthenticated && user ? (
              <>
                {isStaff(user.role) && (
                  <a
                    href={adminToolsUrl()}
                    target="_blank"
                    rel="noreferrer"
                    title={attention.total > 0 ? attention.tooltip : undefined}
                    className="btn-ghost btn-sm relative"
                  >
                    Admin Tools
                    {attention.total > 0 && (
                      <span className="absolute -right-1.5 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-signal px-1 text-[10px] font-bold text-white">
                        {attention.total}
                      </span>
                    )}
                  </a>
                )}
                <Link
                  to="/profile"
                  className="flex items-center gap-2 rounded-full border border-ink/10 py-1 pl-1 pr-3 transition hover:border-ink/30"
                >
                  <Avatar first={user.first_name} last={user.last_name} src={user.avatar_url} size="sm" />
                  <span className="max-w-[9rem] truncate text-sm font-semibold">
                    {user.first_name}
                  </span>
                </Link>
                <button onClick={logout} className="btn-ghost btn-sm">
                  Выйти
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn-ghost btn-sm">
                  Войти
                </Link>
                <Link to="/register" className="btn-primary btn-sm">
                  Регистрация
                </Link>
              </>
            )}
          </div>

          <button
            className="grid h-10 w-10 place-items-center rounded-full border border-ink/15 text-ink md:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Меню"
            aria-expanded={open}
          >
            {open ? <IconX /> : <IconMenu />}
          </button>
        </div>

        {/* Mobile menu — secondary/account actions only. События, Рейтинг and
            the profile are on the fixed bottom tab bar now (see
            MobileTabBar); duplicating them here would just be clutter. */}
        {open && (
          <div className="border-t border-ink/10 bg-paper md:hidden">
            <div className="container-page flex flex-col gap-1 py-4">
              <Link
                to="/support"
                className="flex items-center gap-3 rounded-xl px-4 py-3 text-base font-semibold text-ink hover:bg-ink/[0.05]"
              >
                <IconMail width={18} height={18} />
                Поддержка
                {unreadSupport > 0 && (
                  <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-signal px-1.5 text-[11px] font-bold text-white">
                    {unreadSupport}
                  </span>
                )}
              </Link>
              {isAuthenticated && user ? (
                <>
                  {isStaff(user.role) && (
                    <a
                      href={adminToolsUrl()}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-3 rounded-xl px-4 py-3 text-base font-semibold text-ink hover:bg-ink/[0.05]"
                    >
                      Admin Tools
                      {attention.total > 0 && (
                        <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-signal px-1.5 text-[11px] font-bold text-white">
                          {attention.total}
                        </span>
                      )}
                    </a>
                  )}
                  <Link
                    to="/profile"
                    className="flex items-center gap-3 rounded-xl px-4 py-3 text-base font-semibold text-ink hover:bg-ink/[0.05]"
                  >
                    <IconSettings width={18} height={18} />
                    Настройки профиля
                  </Link>
                  <button onClick={logout} className="btn-ghost mt-1 w-full">
                    Выйти
                  </button>
                </>
              ) : (
                <div className="flex flex-col gap-2">
                  <Link to="/login" className="btn-ghost w-full">
                    Войти
                  </Link>
                  <Link to="/register" className="btn-primary w-full">
                    Регистрация
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <SiteFooter />
      <SurveyReminder pending={surveyPending} />
      <MobileTabBar user={user} surveyPending={surveyPending} />
    </div>
  )
}

function SiteFooter() {
  return (
    <footer className="mt-20 bg-ink text-paper">
      <div className="stripe h-1.5 w-full" />
      <div className="container-page grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2 lg:col-span-2">
          <Brand light />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-paper/60">
            🏃 Воскресные длительные тренировки. Беговое сообщество Чебоксар — события, группы,
            протоколы забегов, маршруты и рейтинг активности участников.
          </p>
          <p className="mt-3 font-mono text-xs uppercase tracking-[0.2em] text-paper/45">
            Чебоксары · #diehardcheb
          </p>
        </div>
        <div>
          <h4 className="font-mono text-xs uppercase tracking-[0.2em] text-volt">Навигация</h4>
          <ul className="mt-4 space-y-2 text-sm text-paper/70">
            <li>
              <Link to="/events" className="hover:text-paper">
                События
              </Link>
            </li>
            <li>
              <Link to="/rating" className="hover:text-paper">
                Рейтинг
              </Link>
            </li>
            <li>
              <Link to="/profile" className="hover:text-paper">
                Профиль
              </Link>
            </li>
            <li>
              <Link to="/support" className="hover:text-paper">
                Поддержка
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <h4 className="font-mono text-xs uppercase tracking-[0.2em] text-volt">Аккаунт</h4>
          <ul className="mt-4 space-y-2 text-sm text-paper/70">
            <li>
              <Link to="/login" className="hover:text-paper">
                Вход
              </Link>
            </li>
            <li>
              <Link to="/register" className="hover:text-paper">
                Регистрация
              </Link>
            </li>
          </ul>
        </div>
      </div>
      <div className="container-page flex flex-col gap-2 border-t border-paper/10 py-6 text-xs text-paper/45 sm:flex-row sm:items-center sm:justify-between">
        <span>© {new Date().getFullYear()} DАЙ ХАРD — беговое сообщество, Чебоксары</span>
        <span className="flex flex-wrap items-center gap-4">
          <InstallAppButton className="hover:text-paper" />
          <Link to="/privacy-policy" className="hover:text-paper">
            Политика обработки персональных данных
          </Link>
          <span className="font-mono">#diehardcheb</span>
        </span>
      </div>
    </footer>
  )
}
