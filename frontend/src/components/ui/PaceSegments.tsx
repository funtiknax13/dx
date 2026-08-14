import type { PaceSegment } from '../../types'
import { formatDistance, segmentPace } from '../../lib/format'
import { IconRoute } from './icons'

/** A group's structured pace plan (warm-up / target / cool-down, progression, …)
 * rendered as a compact stacked list. Used on the group card ("sm") and the
 * group detail page ("md"). A plain single-range plan is handled inline by the
 * callers, so this only ever renders multi-part plans. */
export function PaceSegments({
  segments,
  size = 'sm',
}: {
  segments: PaceSegment[]
  size?: 'sm' | 'md'
}) {
  const text = size === 'md' ? 'text-sm' : 'text-xs'
  return (
    <div className="min-w-0">
      <div className="mb-1 inline-flex items-center gap-1.5 font-mono text-[0.65rem] uppercase tracking-wide text-clay">
        <IconRoute width={13} height={13} className="text-signal" />
        Темп, мин/км
      </div>
      <ul className={`space-y-0.5 ${text}`}>
        {segments.map((s, i) => {
          const pace = segmentPace(s)
          return (
            <li key={i} className="flex flex-wrap items-baseline gap-x-2">
              {s.label && <span className="font-semibold text-ink">{s.label}</span>}
              {s.distance_km != null && (
                <span className="font-mono tabular text-clay">{formatDistance(s.distance_km)}</span>
              )}
              {pace && <span className="font-mono tabular text-ink-600">{pace}</span>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
