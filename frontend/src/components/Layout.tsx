import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { adminToolsUrl } from '../api/client'
import { supportApi } from '../api/support'
import { Avatar } from './ui/Avatar'
import { IconMail, IconMenu, IconX } from './ui/icons'
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
        alt="DАЙ ХАРD"
        className="h-5 w-auto"
      />
    </Link>
  )
}

export function Layout() {
  const { user, isAuthenticated, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const unreadSupport = useUnreadSupportCount(isAuthenticated)

  useEffect(() => setOpen(false), [location.pathname])

  const navItems =
    isAuthenticated && user
      ? [...NAV, { to: `/users/${user.id}`, label: 'Моя статистика' }]
      : NAV

  return (
    <div className="flex min-h-screen flex-col">
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
                    className="btn-ghost btn-sm"
                  >
                    Admin Tools
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

        {/* Mobile menu */}
        {open && (
          <div className="border-t border-ink/10 bg-paper md:hidden">
            <div className="container-page flex flex-col gap-1 py-4">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-xl px-4 py-3 text-base font-semibold ${
                      isActive ? 'bg-ink text-paper' : 'text-ink hover:bg-ink/[0.05]'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
              <div className="my-2 h-px bg-ink/10" />
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
                      className="rounded-xl px-4 py-3 text-base font-semibold text-ink hover:bg-ink/[0.05]"
                    >
                      Admin Tools
                    </a>
                  )}
                  <Link
                    to="/profile"
                    className="flex items-center gap-3 rounded-xl px-4 py-3 hover:bg-ink/[0.05]"
                  >
                    <Avatar first={user.first_name} last={user.last_name} src={user.avatar_url} size="sm" />
                    <span className="font-semibold">{user.first_name} {user.last_name}</span>
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
        <span className="flex items-center gap-4">
          <Link to="/privacy-policy" className="hover:text-paper">
            Политика обработки персональных данных
          </Link>
          <span className="font-mono">#diehardcheb</span>
        </span>
      </div>
    </footer>
  )
}
