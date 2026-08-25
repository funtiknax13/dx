import { useEffect, useRef, useState } from 'react'
import { runningClubsApi, type RunningClubResult } from '../../api/runningClubs'

interface Props {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  invalid?: boolean
  placeholder?: string
}

/** Type-ahead over known running clubs that *also* accepts free text — whatever
 * is typed is kept (and added to the dictionary on save), unlike the strict
 * CityAutocomplete. Picking a suggestion just fills in its canonical spelling. */
export function RunningClubField({ value, onChange, disabled, invalid, placeholder }: Props) {
  const [results, setResults] = useState<RunningClubResult[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const blurTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (!open) {
      setResults([])
      return
    }
    // A blank term lists every known club (see backend) — shown the moment
    // the field gains focus, before anything's typed, so a runner who
    // starts typing a club that's already listed but misspells it can still
    // see it was there instead of unknowingly creating a near-duplicate.
    const term = value.trim()
    const t = window.setTimeout(() => {
      runningClubsApi
        .search(term)
        .then((r) => {
          setResults(r)
          setActive(0)
        })
        .catch(() => setResults([]))
    }, 200)
    return () => window.clearTimeout(t)
  }, [value, open])

  const pick = (c: RunningClubResult) => {
    window.clearTimeout(blurTimer.current)
    onChange(c.title)
    setResults([])
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      pick(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <input
        type="text"
        value={value}
        disabled={disabled}
        placeholder={placeholder ?? 'Начните вводить или выберите из списка'}
        autoComplete="off"
        className={`field disabled:bg-ink/5 disabled:text-clay ${
          invalid ? 'border-danger ring-2 ring-danger/25' : ''
        }`}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onKeyDown={onKeyDown}
        onBlur={() => {
          blurTimer.current = window.setTimeout(() => setOpen(false), 150)
        }}
      />
      {open && !disabled && results.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-ink/10 bg-white py-1 shadow-lift">
          {results.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(c)}
                onMouseEnter={() => setActive(i)}
                className={`flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left text-sm ${
                  i === active ? 'bg-signal-wash' : 'hover:bg-ink/[0.03]'
                }`}
              >
                <span className="font-semibold text-ink">{c.title}</span>
                {c.city && (
                  <span className="shrink-0 truncate font-mono text-[0.7rem] text-clay">
                    {c.city}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
