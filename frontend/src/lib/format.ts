// Formatting helpers — race times, paces, distances, dates (ru-RU).

export function formatDuration(seconds?: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) return '—'
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
}

/** Pace in seconds per km -> "m:ss" (caller appends the "мин/км" unit) */
export function formatPace(secPerKm?: number | null): string {
  if (secPerKm == null || Number.isNaN(secPerKm) || secPerKm <= 0) return '—'
  const m = Math.floor(secPerKm / 60)
  const s = Math.round(secPerKm % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export function formatDistance(km?: number | null): string {
  if (km == null || Number.isNaN(km)) return '—'
  return `${km.toFixed(km % 1 === 0 ? 0 : 2).replace('.', ',')} км`
}

export function formatDate(iso?: string | null, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(
    'ru-RU',
    opts ?? { day: 'numeric', month: 'long', year: 'numeric' },
  )
}

export function formatDateShort(iso?: string | null): string {
  return formatDate(iso, { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// Event/group start times are Cheboksary wall-clock times — pinned to
// Europe/Moscow so every viewer sees the same number regardless of their
// own device's timezone (a race start time isn't a personal instant that
// should shift per viewer).
export function formatTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Moscow',
  })
}

export function isPast(iso?: string | null): boolean {
  if (!iso) return false
  const d = new Date(iso)
  return d.getTime() < Date.now()
}

export function initials(first?: string, last?: string): string {
  const a = (first ?? '').trim()[0] ?? ''
  const b = (last ?? '').trim()[0] ?? ''
  return (a + b).toUpperCase() || '•'
}

export function fullName(first?: string, last?: string): string {
  return [first, last].filter(Boolean).join(' ').trim() || 'Без имени'
}

export function paceRange(min?: string | null, max?: string | null): string | null {
  if (min && max) return `${min}–${max}`
  return min || max || null
}

/** ru pluralization helper: plural(5, 'участник','участника','участников') */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}
