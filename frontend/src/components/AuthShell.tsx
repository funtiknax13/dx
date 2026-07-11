import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { IconCheck, IconSpark, IconX } from './ui/icons'

interface AuthShellProps {
  title: string
  subtitle?: string
  children: ReactNode
  footer?: ReactNode
}

/** Split-screen auth layout: editorial ink panel + form. Stacks on mobile. */
export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <div className="grid min-h-[calc(100vh-4rem)] lg:grid-cols-2">
      {/* Brand / editorial panel — hidden on small screens to keep form front & center */}
      <aside className="relative hidden overflow-hidden bg-ink text-paper lg:block">
        <div
          className="absolute inset-0 opacity-80"
          style={{
            backgroundImage:
              'radial-gradient(60% 70% at 20% 20%, rgba(255,255,255,0.12), transparent 60%), radial-gradient(50% 60% at 90% 90%, rgba(255,255,255,0.06), transparent 60%)',
          }}
        />
        <div className="stripe absolute inset-x-0 top-0 h-1.5" />
        <div className="relative flex h-full flex-col justify-between p-12">
          <Link to="/events" className="flex items-center gap-2.5">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-paper/10 text-volt">
              <span className="font-display text-base font-black leading-none tracking-tighter" aria-hidden>
                DX
              </span>
            </span>
            <span className="font-display text-xl tracking-tightest">DАЙ ХАРD</span>
          </Link>

          <div>
            <IconSpark className="mb-5 text-volt" width={32} height={32} />
            <h2 className="max-w-md font-display text-4xl leading-[1.05]">
              Каждый забег — <span className="text-paper/60">строка</span> в твоём протоколе.
            </h2>
            <p className="mt-4 max-w-sm text-paper/60">
              🏃 Воскресные длительные тренировки. Беговое сообщество Чебоксар — старты, маршруты и
              живой рейтинг участников.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-x-8 gap-y-2 font-mono text-xs text-paper/50">
            <span>Чебоксары</span>
            <span>#diehardcheb</span>
          </div>
        </div>
      </aside>

      {/* Form panel */}
      <main className="flex items-center justify-center px-5 py-12 sm:px-8">
        <div className="w-full max-w-md animate-fade-up">
          <div className="mb-8">
            <h1 className="font-display text-3xl sm:text-4xl">{title}</h1>
            {subtitle && <p className="mt-2 text-ink-600">{subtitle}</p>}
          </div>
          {children}
          {footer && <div className="mt-8 text-sm text-ink-600">{footer}</div>}
        </div>
      </main>
    </div>
  )
}

export function FormError({ message }: { message?: string | null }) {
  if (!message) return null
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-ink/20 bg-ink/[0.04] px-4 py-3 text-sm text-ink">
      <IconX className="mt-0.5 shrink-0 text-ink-600" width={15} height={15} />
      <span>{message}</span>
    </div>
  )
}

export function FormSuccess({ message }: { message?: string | null }) {
  if (!message) return null
  return (
    <div className="flex items-start gap-2.5 rounded-xl bg-ink px-4 py-3 text-sm text-paper">
      <IconCheck className="mt-0.5 shrink-0 text-volt" width={15} height={15} />
      <span>{message}</span>
    </div>
  )
}
