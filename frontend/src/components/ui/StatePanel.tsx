import type { ReactNode } from 'react'

interface StatePanelProps {
  title: string
  description?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  tone?: 'neutral' | 'error'
}

export function StatePanel({ title, description, icon, action, tone = 'neutral' }: StatePanelProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 rounded-xl2 border border-dashed px-6 py-16 text-center ${
        tone === 'error' ? 'border-signal/40 bg-signal-wash/40' : 'border-ink/15 bg-white/40'
      }`}
    >
      {icon && (
        <div className="grid h-14 w-14 place-items-center rounded-full bg-ink text-volt">{icon}</div>
      )}
      <h3 className="font-display text-xl text-ink">{title}</h3>
      {description && <p className="max-w-md text-sm text-ink-600">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
