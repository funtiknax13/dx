import type { ComponentType, SVGProps } from 'react'
import { NavLink } from 'react-router-dom'
import { Avatar } from './ui/Avatar'
import { IconCalendar, IconTrophy, IconUser } from './ui/icons'
import type { User } from '../types'

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>

const ITEMS: { to: string; label: string; icon: IconComponent }[] = [
  { to: '/events', label: 'События', icon: IconCalendar },
  { to: '/rating', label: 'Рейтинг', icon: IconTrophy },
]

/** Bottom tab bar, mobile only (md:hidden) — fixed, no scroll-based hide/show.
 * Replaces the hamburger as the primary way to move between the screens
 * people actually open every day (events, rating, own stats); everything
 * else (support, admin tools, logout) stays in the hamburger drawer. The
 * third tab goes to the same "Моя статистика" destination as the desktop
 * nav (own public profile — stats/achievements/history), shown as the
 * runner's avatar once logged in, or "Войти" otherwise. Safe-area aware so
 * it doesn't collide with the iOS home-indicator gesture zone. */
export function MobileTabBar({
  user,
  surveyPending,
}: {
  user: User | null
  surveyPending: boolean
}) {
  const profileTo = user ? `/users/${user.id}` : '/login'
  const itemCls = ({ isActive }: { isActive: boolean }) =>
    `flex flex-1 flex-col items-center justify-center gap-0.5 text-[0.65rem] font-semibold transition ${
      isActive ? 'text-ink' : 'text-clay'
    }`

  return (
    <nav
      aria-label="Главное меню"
      className="fixed inset-x-0 bottom-0 z-40 flex h-16 border-t border-ink/10 bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
    >
      {ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} className={itemCls}>
          {({ isActive }) => (
            <>
              <span className="relative">
                <Icon width={22} height={22} strokeWidth={isActive ? 2.2 : 1.8} />
                {to === '/rating' && surveyPending && (
                  <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-danger" />
                )}
              </span>
              {label}
            </>
          )}
        </NavLink>
      ))}
      <NavLink to={profileTo} className={itemCls}>
        {user ? (
          <>
            <Avatar first={user.first_name} last={user.last_name} src={user.avatar_url} size="sm" />
            Статистика
          </>
        ) : (
          <>
            <IconUser width={22} height={22} />
            Войти
          </>
        )}
      </NavLink>
    </nav>
  )
}
