import { api } from './client'
import { attendanceApi } from './attendance'
import type {
  ChangePasswordPayload,
  ParticipationEntry,
  PublicProfile,
  UpdateProfilePayload,
  User,
} from '../types'

// Raw shapes as actually returned by the backend (see backend/app/schemas/user.py) —
// kept private to this module.
interface RawUser {
  id: number
  first_name: string
  last_name: string
  email: string
  role: User['role']
  city?: string | null
  gender?: User['gender']
  birthday?: string | null
  phone?: string | null
  avatar?: string | null
}

interface RawHistoryItem {
  attendance_id: number
  group_id: number
  group_name: string
  event_id: number
  event_title: string
  event_date: string
  finish_status: string
  has_result: boolean
}

interface RawPublicProfile {
  id: number
  first_name: string
  last_name: string
  avatar?: string | null
  rating: number
  history: RawHistoryItem[]
}

/** Full self-service data export (152-FZ art. 14 "right to access") — passed
 * straight through to a downloaded JSON file, no need to reshape it. */
export interface AccountExport {
  profile: RawUser
  account_created_at: string
  privacy_accepted_at: string | null
  history: Array<{
    attendance_id: number
    group_id: number
    group_name: string
    event_id: number
    event_title: string
    event_date: string
    finish_status: string
    distance_km: number | null
    duration_seconds: number | null
    pace_seconds_per_km: number | null
    moderation_status: string | null
  }>
  signups: Array<{
    signup_id: number
    group_id: number
    group_name: string
    event_id: number
    event_title: string
    event_date: string
  }>
}

function mapUser(raw: RawUser): User {
  return { ...raw, avatar_url: raw.avatar ?? null }
}

async function mapHistoryItem(raw: RawHistoryItem): Promise<ParticipationEntry> {
  const base: ParticipationEntry = {
    attendance_id: raw.attendance_id,
    event_id: raw.event_id,
    event_title: raw.event_title,
    group_id: raw.group_id,
    group_name: raw.group_name,
    date: raw.event_date,
    finish_status: raw.finish_status as ParticipationEntry['finish_status'],
    has_result: raw.has_result,
  }
  if (!raw.has_result) return base
  // Enrich with the actual time/distance/pace — the history endpoint only tells us
  // *that* a result exists, not its numbers, so fetch it (small history lists, fine
  // to do in parallel per-item rather than adding a dedicated batch endpoint).
  try {
    const result = await attendanceApi.getResult(raw.attendance_id)
    return {
      ...base,
      distance_km: result.distance_km,
      duration_seconds: result.duration_seconds,
      pace_seconds_per_km: result.pace_seconds_per_km,
    }
  } catch {
    return base
  }
}

async function mapPublicProfile(raw: RawPublicProfile): Promise<PublicProfile> {
  const history = await Promise.all(raw.history.map(mapHistoryItem))
  return {
    id: raw.id,
    first_name: raw.first_name,
    last_name: raw.last_name,
    avatar_url: raw.avatar ?? null,
    rating: raw.rating,
    finished_count: raw.rating,
    history,
  }
}

export const usersApi = {
  me: async () => mapUser(await api.get<RawUser>('/users/me')),

  updateMe: async (payload: UpdateProfilePayload) =>
    mapUser(await api.patch<RawUser>('/users/me', payload)),

  uploadAvatar: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return mapUser(await api.post<RawUser>('/users/me/avatar', form))
  },

  changePassword: (payload: ChangePasswordPayload) =>
    api.post<{ message?: string }>('/users/me/password', payload),

  publicProfile: async (id: number | string) =>
    mapPublicProfile(await api.get<RawPublicProfile>(`/users/${id}`)),

  exportMe: () => api.get<AccountExport>('/users/me/export'),

  deleteMe: (password: string) =>
    api.del<{ message?: string }>('/users/me', { password }),
}
