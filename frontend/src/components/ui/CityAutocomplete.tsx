import { useEffect, useRef, useState } from 'react'
import { citiesApi, type CityResult } from '../../api/cities'

interface Props {
  /** Committed display name (e.g. "Чебоксары"), '' when none. */
  value: string
  /** Fired on pick (city) or clear (null). */
  onSelect: (city: CityResult | null) => void
  label?: string
  error?: string
  placeholder?: string
}

function cityLabel(c: CityResult): string {
  return [c.region, c.country].filter(Boolean).join(', ')
}

/** Type-ahead over the canonical city list. Typing only drives search; the
 * committed value changes only when the user picks an option or clears — so
 * half-typed text never gets saved. */
export function CityAutocomplete({ value, onSelect, label = 'Город', error, placeholder }: Props) {
  const [query, setQuery] = useState(value)
  const [results, setResults] = useState<CityResult[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const blurTimer = useRef<number | undefined>(undefined)

  // Keep the input in sync when the committed value changes externally.
  useEffect(() => {
    setQuery(value)
  }, [value])

  // Debounced search as the user types.
  useEffect(() => {
    const term = query.trim()
    if (!open || term.length < 2 || term === value) {
      setResults([])
      return
    }
    const t = window.setTimeout(() => {
      citiesApi
        .search(term)
        .then((r) => {
          setResults(r)
          setActive(0)
        })
        .catch(() => setResults([]))
    }, 200)
    return () => window.clearTimeout(t)
  }, [query, open, value])

  const pick = (c: CityResult) => {
    window.clearTimeout(blurTimer.current)
    onSelect(c)
    setQuery(c.name)
    setResults([])
    setOpen(false)
  }

  const clear = () => {
    onSelect(null)
    setQuery('')
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
    <div className="relative" ref={boxRef}>
      <label className="field-label">{label}</label>
      <div className="relative">
        <input
          type="text"
          value={query}
          placeholder={placeholder ?? 'Начните вводить город'}
          autoComplete="off"
          className="field pr-9"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onKeyDown={onKeyDown}
          onBlur={() => {
            // Delay so a click on an option still registers; then revert the
            // text to the committed value if nothing new was picked.
            blurTimer.current = window.setTimeout(() => {
              setOpen(false)
              setQuery(value)
            }, 150)
          }}
        />
        {(query || value) && (
          <button
            type="button"
            aria-label="Очистить"
            onMouseDown={(e) => e.preventDefault()}
            onClick={clear}
            className="absolute right-2 top-1/2 -translate-y-1/2 grid h-6 w-6 place-items-center rounded-full text-clay hover:bg-ink/5 hover:text-ink"
          >
            ×
          </button>
        )}
      </div>

      {open && results.length > 0 && (
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
                <span className="font-semibold text-ink">{c.name}</span>
                <span className="shrink-0 truncate font-mono text-[0.7rem] text-clay">
                  {cityLabel(c)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="mt-1.5 text-xs text-signal-600">{error}</p>}
    </div>
  )
}
