import { NavLink } from 'react-router-dom'
import tabCalendarIcon from '../assets/icons/tab-calendar.png'
import tabTrophyIcon from '../assets/icons/tab-trophy.png'
import tabRunningIcon from '../assets/icons/tab-running.png'
import tabSettingsIcon from '../assets/icons/tab-settings.png'
import tabUserIcon from '../assets/icons/tab-user.png'
import type { User } from '../types'

interface TabItem {
  to: string
  label: string
  icon: string
}

const BASE_ITEMS: TabItem[] = [
  { to: '/events', label: 'События', icon: tabCalendarIcon },
  { to: '/rating', label: 'Рейтинг', icon: tabTrophyIcon },
]

/** Bottom tab bar, mobile only (md:hidden) — fixed, no scroll-based hide/show.
 * Icons are raster PNGs cropped from one AI-generated reference sheet (not
 * the shared SVG set used elsewhere) so all four share one consistent style;
 * a flat PNG can't recolor via currentColor, so active/inactive is faked
 * with opacity instead of the SVG icons' color+strokeWidth swap.
 * Anonymous visitors get 3 tabs (events, rating, "Войти" — a stats/profile
 * tab would be nothing but another login prompt, redundant with it).
 * Logged-in runners get all 4: own stats (same "Моя статистика" destination
 * as the desktop nav) and profile settings each get their own tab instead of
 * living in the hamburger drawer. Safe-area aware so it doesn't collide with
 * the iOS home-indicator gesture zone. */
export function MobileTabBar({ user }: { user: User | null }) {
  const items: TabItem[] = user
    ? [
        ...BASE_ITEMS,
        { to: `/users/${user.id}`, label: 'Статистика', icon: tabRunningIcon },
        { to: '/profile', label: 'Профиль', icon: tabSettingsIcon },
      ]
    : [...BASE_ITEMS, { to: '/login', label: 'Войти', icon: tabUserIcon }]

  const itemCls = ({ isActive }: { isActive: boolean }) =>
    `flex flex-1 flex-col items-center justify-center gap-0.5 text-[0.65rem] font-semibold transition ${
      isActive ? 'text-ink' : 'text-clay'
    }`

  return (
    <nav
      aria-label="Главное меню"
      className="fixed inset-x-0 bottom-0 z-40 flex h-16 border-t border-ink/10 bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
    >
      {items.map(({ to, label, icon }) => (
        <NavLink key={to} to={to} className={itemCls}>
          {({ isActive }) => (
            <>
              <img
                src={icon}
                alt=""
                className={`h-[22px] w-auto transition-opacity ${isActive ? 'opacity-100' : 'opacity-55'}`}
              />
              {label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
