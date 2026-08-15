import type { PaceSegment } from '../../types'
import { formatDistance, segmentPace } from '../../lib/format'

/** A group's structured pace plan (warm-up / target / cool-down, progression, …)
 * rendered as one flowing line of text — reads like the plain single-range
 * pace it replaces instead of a boxed table. Plain <span>s (not flex), so the
 * browser wraps at word boundaries and can never force horizontal overflow,
 * even on a narrow phone screen. Each segment always shows its km — knowing
 * how far a given pace lasts is the whole point of a structured plan; "md"
 * (the group page) is just a bigger font than "sm" (the card). A plain
 * single-range plan is rendered inline by the callers instead of through this
 * component. */
export function PaceSegments({
  segments,
  size = 'sm',
  className = '',
}: {
  segments: PaceSegment[]
  size?: 'sm' | 'md'
  className?: string
}) {
  const textSize = size === 'md' ? 'text-sm' : 'text-xs'
  // Unit shown once, attached to the first segment that actually has a pace
  // (normally the first one) — implied for the rest of the line.
  const firstPaceIndex = segments.findIndex((s) => segmentPace(s))
  return (
    <p className={`${textSize} leading-relaxed text-ink-600 ${className}`}>
      {segments.map((s, i) => {
        const pace = segmentPace(s)
        const km = s.distance_km != null ? formatDistance(s.distance_km) : null
        return (
          <span key={i}>
            {i > 0 && <span className="text-clay"> · </span>}
            {s.label && <span className="font-semibold text-ink">{s.label} </span>}
            {km && (
              <span className="font-mono tabular font-semibold text-ink">
                {km}
                <span className="font-normal text-clay"> — </span>
              </span>
            )}
            {pace && (
              <span className="font-mono tabular">
                {pace}
                {i === firstPaceIndex && <span className="text-clay"> мин/км</span>}
              </span>
            )}
          </span>
        )
      })}
    </p>
  )
}
