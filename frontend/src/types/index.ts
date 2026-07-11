// Domain types — mirror the backend API contract (base path /api/v1).
// Kept in one place so wiring real responses later is a matter of matching shapes.

export type Role = 'runner' | 'organizer' | 'admin'
export type Gender = 'male' | 'female' | 'other'
export type FinishStatus = 'finished' | 'dnf'
export type ModerationStatus = 'pending' | 'approved'

export interface Tokens {
  access_token: string
  refresh_token: string
  token_type?: string
}

export interface User {
  id: number
  first_name: string
  last_name: string
  email: string
  role: Role
  city?: string | null
  gender?: Gender | null
  birthday?: string | null // ISO date
  phone?: string | null
  avatar_url?: string | null
  rating?: number | null
  created_at?: string
}

/** Public profile — private fields (email, phone, birthday, city, gender) are omitted server-side. */
export interface PublicProfile {
  id: number
  first_name: string
  last_name: string
  avatar_url?: string | null
  rating: number
  finished_count: number
  history: ParticipationEntry[]
}

export interface ParticipationEntry {
  attendance_id: number
  event_id: number
  event_title: string
  group_id: number
  group_name: string
  location?: string | null
  date: string // ISO
  finish_status: FinishStatus
  distance_km?: number | null
  duration_seconds?: number | null
  pace_seconds_per_km?: number | null
  place?: number | null
  /** False when the runner hasn't submitted a result for this attendance yet. */
  has_result?: boolean
}

export interface EventPhoto {
  id: number
  url: string
  thumbnail_url?: string | null
  caption?: string | null
}

export interface EventSummary {
  id: number
  title: string
  date: string // ISO
  description?: string | null
  cover_url?: string | null
  location_summary?: string | null
  group_count?: number
  participant_count?: number
}

export interface EventDetail extends EventSummary {
  photos: EventPhoto[]
  groups: Group[]
}

export interface Group {
  id: number
  event_id: number
  name: string
  location?: string | null
  distance_code?: string | null
  pace_min?: string | null // e.g. "5:40"
  pace_max?: string | null // e.g. "5:30"
  target_distance_km?: number | null
  start_time?: string | null // ISO
  has_route_gpx?: boolean
  signup_count?: number
  finisher_count?: number
}

export interface Signup {
  id: number
  group_id: number
  user_id: number
  created_at: string
}

/** Current user's signup state for a group. */
export interface GroupSignupState {
  signed_up: boolean
  signup_id?: number | null
}

export interface ProtocolRow {
  attendance_id: number
  place?: number | null
  runner_id?: number | null // null = unmatched (no account yet)
  runner_name: string
  avatar_url?: string | null
  finish_status: FinishStatus
  distance_km?: number | null
  duration_seconds?: number | null
  pace_seconds_per_km?: number | null
}

export interface Protocol {
  group_id: number
  finishers: ProtocolRow[] // sorted by time ascending (server-side)
  pending: ProtocolRow[] // on the list, but no confirmed result yet
  dnf: ProtocolRow[]
}

export interface TrackPoint {
  lat: number
  lng: number
  ele?: number | null
}

export interface ElevationPoint {
  distance_km: number
  ele: number
}

export interface RouteMap {
  points: TrackPoint[]
  elevation: ElevationPoint[]
  distance_km?: number | null
  ascent_m?: number | null
  descent_m?: number | null
  bounds?: [[number, number], [number, number]] | null
}

export interface RatingEntry {
  rank: number
  user_id: number
  first_name: string
  last_name: string
  avatar_url?: string | null
  city?: string | null
  finished_count: number
  score: number
}

export type RatingPeriod = 'all' | 'year' | 'month'

// ---- Request payloads ----

export interface RegisterPayload {
  first_name: string
  last_name: string
  email: string
  password: string
}

export interface LoginPayload {
  email: string
  password: string
}

export interface UpdateProfilePayload {
  first_name?: string
  last_name?: string
  city?: string | null
  gender?: Gender | null
  birthday?: string | null
  phone?: string | null
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
}

export interface Paginated<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}

/** A guest profile auto-created from CSV import when no email matched a
 * registered account. Can be claimed by a real user ("this is me"). */
export interface GuestProfile {
  id: number
  first_name: string
  last_name: string
  avatar_url?: string | null
}

export type ClaimStatus = 'pending' | 'approved' | 'rejected'

export interface GuestClaim {
  id: number
  guest_user_id: number
  claimant_user_id: number
  status: ClaimStatus
  created_at: string
  decided_at?: string | null
  guest: GuestProfile
}
