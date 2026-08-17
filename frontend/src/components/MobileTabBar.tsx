import type { ComponentType, SVGProps } from 'react'
import { NavLink } from 'react-router-dom'
import { IconCalendar, IconSettings, IconTrophy, IconUser } from './ui/icons'
import tabRunningIcon from '../assets/icons/tab-running.png'
import type { User } from '../types'

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>

interface TabItem {
  to: string
  label: string
  // Either the shared SVG icon set (recolors via currentColor, so the
  // active/inactive state is a plain color change) or a static raster asset
  // (Статистика — a hand-supplied reference image; opacity fakes the same
  // active/inactive distinction since a flat PNG can't recolor at runtime).
  icon: IconComponent | { src: string }
}

const BASE_ITEMS: TabItem[] = [
  { to: '/events', label: 'События', icon: IconCalendar },
  { to: '/rating', label: 'Рейтинг', icon: IconTrophy },
]

/** Bottom tab bar, mobile only (md:hidden) — fixed, no scroll-based hide/show.
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
        { to: `/users/${user.id}`, label: 'Статистика', icon: { src: tabRunningIcon } },
        { to: '/profile', label: 'Профиль', icon: IconSettings },
      ]
    : [...BASE_ITEMS, { to: '/login', label: 'Войти', icon: IconUser }]

  const itemCls = ({ isActive }: { isActive: boolean }) =>
    `flex flex-1 flex-col items-center justify-center gap-0.5 text-[0.65rem] font-semibold transition ${
      isActive ? 'text-ink' : 'text-clay'
    }`

  return (
    <nav
      aria-label="Главное меню"
      className="fixed inset-x-0 bottom-0 z-40 flex h-16 border-t border-ink/10 bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
    >
      {items.map(({ to, label, icon }) => {
        const Icon = 'src' in icon ? null : icon
        return (
          <NavLink key={to} to={to} className={itemCls}>
            {({ isActive }) =>
              Icon ? (
                <>
                  <Icon width={22} height={22} strokeWidth={isActive ? 2.2 : 1.8} />
                  {label}
                </>
              ) : (
                <>
                  <img
                    src={(icon as { src: string }).src}
                    alt=""
                    className={`h-[22px] w-auto transition-opacity ${isActive ? 'opacity-100' : 'opacity-55'}`}
                  />
                  {label}
                </>
              )
            }
          </NavLink>
        )
      })}
    </nav>
  )
}
