import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { adminToolsUrl } from '../api/client'
import { Avatar } from './ui/Avatar'
import { IconMenu, IconX } from './ui/icons'

function isStaff(role?: string) {
  return role === 'organizer' || role === 'admin'
}

const NAV = [
  { to: '/events', label: 'События' },
  { to: '/rating', label: 'Рейтинг' },
]

function Brand({ onClick }: { onClick?: () => void }) {
  return (
    <Link to="/events" onClick={onClick} className="group flex items-center gap-2.5">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ink text-volt shadow-sm transition-transform group-hover:-rotate-6">
        <span className="font-display text-sm font-black leading-none tracking-tighter" aria-hidden>
          DX
        </span>
      </span>
      <span className="font-display text-lg font-extrabold leading-none tracking-tightest">
        DАЙ ХАРD
      </span>
    </Link>
  )
}

export function Layout() {
  const { user, isAuthenticated, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()

  useEffect(() => setOpen(false), [location.pathname])

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-ink/10 bg-paper/85 backdrop-blur-md">
        <div className="container-page flex h-16 items-center justify-between gap-4">
          <div className="flex items-center gap-8">
            <Brand />
            <nav className="hidden items-center gap-1 md:flex">
              {NAV.map((item) => (
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
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `rounded-xl px-4 py-3 text-base font-semibold ${
                      isActive ? 'bg-ink text-paper' : 'text-ink hover:bg-ink/[0.05]'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
              <div className="my-2 h-px bg-ink/10" />
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
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-paper/10 text-volt">
              <span className="font-display text-sm font-black leading-none tracking-tighter" aria-hidden>
                DX
              </span>
            </span>
            <span className="font-display text-lg tracking-tightest">DАЙ ХАРD</span>
          </div>
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
        <span className="font-mono">#diehardcheb</span>
      </div>
    </footer>
  )
}
