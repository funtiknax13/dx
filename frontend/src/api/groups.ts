import { api } from './client'
import type {
  Group,
  GroupSignupState,
  Protocol,
  ProtocolRow,
  RouteMap,
  SignupRoster,
} from '../types'

// Raw shapes as actually returned by the backend (see backend/app/schemas/group.py) —
// kept private to this module; every exported method returns the frontend's own
// types via the mappers below.
interface RawGroup {
  id: number
  event_id: number
  location: string
  name: string
  distance_code?: string | null
  target_distance_km: number
  pace_min?: string | null
  pace_max?: string | null
  start_time?: string | null
  start_lat?: number | null
  start_lng?: number | null
  route_gpx?: string | null
  event_date: string
  signup_count: number
}

interface RawProtocolEntry {
  rank: number | null
  attendance_id: number
  runner_id: number | null
  display_name: string
  avatar: string | null
  latest_achievement: number | null
  distance_km: number | null
  duration_seconds: number | null
  pace_seconds_per_km: number | null
  finish_status: string
  moderation_status: string | null
}

interface RawProtocol {
  group_id: number
  group_ids: number[]
  finishers: RawProtocolEntry[]
  pending: RawProtocolEntry[]
  dnf: RawProtocolEntry[]
}

interface RawRoutePoint {
  lat: number
  lon: number
  ele?: number | null
}

interface RawRouteMap {
  track_points: RawRoutePoint[]
  elevation_profile: { distance_km: number; ele: number | null }[]
  distance_km: number
}

function mapGroup(raw: RawGroup): Group {
  return {
    id: raw.id,
    event_id: raw.event_id,
    name: raw.name,
    location: raw.location,
    distance_code: raw.distance_code ?? null,
    pace_min: raw.pace_min ?? null,
    pace_max: raw.pace_max ?? null,
    target_distance_km: raw.target_distance_km,
    start_time: raw.start_time ?? null,
    start_lat: raw.start_lat ?? null,
    start_lng: raw.start_lng ?? null,
    event_date: raw.event_date,
    has_route_gpx: Boolean(raw.route_gpx),
    signup_count: raw.signup_count,
  }
}

function mapProtocolEntry(raw: RawProtocolEntry): ProtocolRow {
  return {
    attendance_id: raw.attendance_id,
    place: raw.rank,
    runner_id: raw.runner_id,
    runner_name: raw.display_name,
    avatar_url: raw.avatar,
    latest_achievement: raw.latest_achievement,
    finish_status: raw.finish_status as ProtocolRow['finish_status'],
    distance_km: raw.distance_km,
    duration_seconds: raw.duration_seconds,
    pace_seconds_per_km: raw.pace_seconds_per_km,
    moderation_status: raw.moderation_status as ProtocolRow['moderation_status'],
  }
}

function mapProtocol(raw: RawProtocol): Protocol {
  return {
    group_id: raw.group_id,
    group_ids: raw.group_ids,
    finishers: raw.finishers.map(mapProtocolEntry),
    pending: raw.pending.map(mapProtocolEntry),
    dnf: raw.dnf.map(mapProtocolEntry),
  }
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

function mapRouteMap(raw: RawRouteMap): RouteMap {
  const { ascent, descent } = elevationGain(raw.elevation_profile)
  return {
    points: raw.track_points.map((p) => ({ lat: p.lat, lng: p.lon, ele: p.ele })),
    elevation: raw.elevation_profile.map((p) => ({ distance_km: p.distance_km, ele: p.ele ?? 0 })),
    distance_km: raw.distance_km,
    ascent_m: ascent,
    descent_m: descent,
  }
}

interface RawSignupRosterEntry {
  signup_id: number
  runner_id: number
  display_name: string
  avatar?: string | null
}

interface RawSignupRoster {
  group_id: number
  count: number
  entries: RawSignupRosterEntry[]
}

function mapSignupRoster(raw: RawSignupRoster): SignupRoster {
  return {
    group_id: raw.group_id,
    count: raw.count,
    entries: raw.entries.map((e) => ({
      signup_id: e.signup_id,
      runner_id: e.runner_id,
      display_name: e.display_name,
      avatar_url: e.avatar ?? null,
    })),
  }
}

export const groupsApi = {
  list: async (eventId: number | string) =>
    (await api.get<RawGroup[]>(`/events/${eventId}/groups`)).map(mapGroup),

  detail: async (id: number | string) => mapGroup(await api.get<RawGroup>(`/groups/${id}`)),

  update: async (id: number | string, payload: Partial<RawGroup>) =>
    mapGroup(await api.patch<RawGroup>(`/groups/${id}`, payload)),

  protocol: async (id: number | string) =>
    mapProtocol(await api.get<RawProtocol>(`/groups/${id}/protocol`)),

  routeMap: async (id: number | string) =>
    mapRouteMap(await api.get<RawRouteMap>(`/groups/${id}/route-map`)),

  /** Absolute URL for downloading the raw GPX file. */
  routeGpxUrl: (id: number | string) => `${api.apiUrl}/groups/${id}/route-gpx`,

  signupState: (id: number | string) => api.get<GroupSignupState>(`/groups/${id}/signups/me`),

  signupRoster: async (id: number | string) =>
    mapSignupRoster(await api.get<RawSignupRoster>(`/groups/${id}/signups`)),

  uploadRouteGpx: async (id: number | string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return mapGroup(await api.post<RawGroup>(`/groups/${id}/route-gpx`, form))
  },
}
