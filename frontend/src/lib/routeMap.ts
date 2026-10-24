import type { RouteMap } from '../types'

// Raw shape as returned by any backend "parse this GPX" endpoint (see
// backend/app/schemas/group.py's RouteMap, reused verbatim for the contest
// entry route-map endpoint) — shared so groups and contests don't each
// duplicate the elevation-gain math below.
export interface RawRoutePoint {
  lat: number
  lon: number
  ele?: number | null
}

export interface RawRouteMap {
  track_points: RawRoutePoint[]
  elevation_profile: { distance_km: number; ele: number | null }[]
  distance_km: number
}

function elevationGain(profile: { ele: number | null }[]): { ascent: number; descent: number } {
  let ascent = 0
  let descent = 0
  for (let i = 1; i < profile.length; i++) {
    const prev = profile[i - 1].ele
    const cur = profile[i].ele
    if (prev == null || cur == null) continue
    const delta = cur - prev
    if (delta > 0) ascent += delta
    else descent += -delta
  }
  return { ascent, descent }
}

export function mapRouteMap(raw: RawRouteMap): RouteMap {
  const { ascent, descent } = elevationGain(raw.elevation_profile)
  return {
    points: raw.track_points.map((p) => ({ lat: p.lat, lng: p.lon, ele: p.ele })),
    elevation: raw.elevation_profile.map((p) => ({ distance_km: p.distance_km, ele: p.ele ?? 0 })),
    distance_km: raw.distance_km,
    ascent_m: ascent,
    descent_m: descent,
  }
}
