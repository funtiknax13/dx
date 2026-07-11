import { useMemo, useState } from 'react'
import type { ElevationPoint } from '../types'

interface Props {
  data: ElevationPoint[]
  ascent?: number | null
  descent?: number | null
}

const W = 720
const H = 220
const PAD = { top: 16, right: 16, bottom: 28, left: 40 }

/** Dependency-free SVG area chart for the route elevation profile. */
export function ElevationProfile({ data, ascent, descent }: Props) {
  const [hover, setHover] = useState<number | null>(null)

  const model = useMemo(() => {
    if (data.length < 2) return null
    const xs = data.map((d) => d.distance_km)
    const ys = data.map((d) => d.ele)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const spanY = Math.max(maxY - minY, 1)
    const padY = spanY * 0.15

    const plotW = W - PAD.left - PAD.right
    const plotH = H - PAD.top - PAD.bottom

    const sx = (x: number) => PAD.left + ((x - minX) / Math.max(maxX - minX, 1e-6)) * plotW
    const sy = (y: number) =>
      PAD.top + plotH - ((y - (minY - padY)) / (spanY + padY * 2)) * plotH

    const pts = data.map((d) => ({ x: sx(d.distance_km), y: sy(d.ele), raw: d }))
    const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
    const area = `${line} L${pts[pts.length - 1].x.toFixed(1)},${(H - PAD.bottom).toFixed(
      1,
    )} L${pts[0].x.toFixed(1)},${(H - PAD.bottom).toFixed(1)} Z`

    // y gridlines
    const yTicks = [minY, (minY + maxY) / 2, maxY].map((v) => ({ v, y: sy(v) }))
    return { pts, line, area, minX, maxX, minY, maxY, yTicks, plotH }
  }, [data])

  if (!model) {
    return (
      <div className="rounded-xl2 border border-dashed border-ink/15 bg-white/50 px-6 py-10 text-center text-sm text-ink-600">
        Профиль высоты недоступен для этого маршрута.
      </div>
    )
  }

  const active = hover != null ? model.pts[hover] : null

  return (
    <div className="rounded-xl2 border border-ink/[0.08] bg-white p-4 shadow-card">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-ink-600">
          Профиль высоты
        </span>
        <div className="flex gap-3 font-mono text-xs tabular text-ink-600">
          {ascent != null && <span className="text-signal">↑ {Math.round(ascent)} м</span>}
          {descent != null && <span className="text-clay">↓ {Math.round(descent)} м</span>}
        </div>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full touch-none"
        role="img"
        aria-label="График профиля высоты маршрута"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const x = ((e.clientX - rect.left) / rect.width) * W
          let nearest = 0
          let best = Infinity
          model.pts.forEach((p, i) => {
            const d = Math.abs(p.x - x)
            if (d < best) {
              best = d
              nearest = i
            }
          })
          setHover(nearest)
        }}
      >
        <defs>
          <linearGradient id="eleFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0E0E0D" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#0E0E0D" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* gridlines */}
        {model.yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={t.y}
              y2={t.y}
              stroke="#0E0E0D"
              strokeOpacity={0.08}
              strokeDasharray="3 4"
            />
            <text x={PAD.left - 6} y={t.y + 3} textAnchor="end" className="fill-ink-600" fontSize="10" fontFamily="JetBrains Mono, monospace">
              {Math.round(t.v)}
            </text>
          </g>
        ))}

        <path d={model.area} fill="url(#eleFill)" />
        <path d={model.line} fill="none" stroke="#0E0E0D" strokeWidth={2.2} strokeLinejoin="round" />

        {/* x labels */}
        <text x={PAD.left} y={H - 8} className="fill-ink-600" fontSize="10" fontFamily="JetBrains Mono, monospace">
          0 км
        </text>
        <text x={W - PAD.right} y={H - 8} textAnchor="end" className="fill-ink-600" fontSize="10" fontFamily="JetBrains Mono, monospace">
          {model.maxX.toFixed(1)} км
        </text>

        {active && (
          <g>
            <line
              x1={active.x}
              x2={active.x}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke="#0E0E0D"
              strokeOpacity={0.35}
            />
            <circle cx={active.x} cy={active.y} r={4.5} fill="#0E0E0D" stroke="#fff" strokeWidth={2} />
            <g transform={`translate(${Math.min(Math.max(active.x, 54), W - 54)}, ${PAD.top + 2})`}>
              <rect x={-52} y={-2} width={104} height={34} rx={7} fill="#0E0E0D" />
              <text x={0} y={12} textAnchor="middle" fill="#F7F7F5" fontSize="11" fontFamily="JetBrains Mono, monospace">
                {active.raw.ele.toFixed(0)} м
              </text>
              <text x={0} y={25} textAnchor="middle" fill="#B4B4AF" fontSize="10" fontFamily="JetBrains Mono, monospace">
                {active.raw.distance_km.toFixed(2)} км
              </text>
            </g>
          </g>
        )}
      </svg>
    </div>
  )
}
