import { api } from './client'
import { attendanceApi } from './attendance'
import type {
  Achievement,
  ChangePasswordPayload,
  Paginated,
  ParticipationEntry,
  PriorExperience,
  PublicProfile,
  StatsLockReason,
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
  running_club?: string | null
  prior_experience?: PriorExperience | null
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

interface RawAchievement {
  threshold: number
  reached: boolean
  reached_at?: string | null
  event_id?: number | null
  event_title?: string | null
}

interface RawPublicProfile {
  id: number
  first_name: string
  last_name: string
  avatar?: string | null
  is_guest: boolean
  registered_at?: string | null
  lock_reason: StatsLockReason
  missing_fields: string[]
  rating: number | null
  first_run_date?: string | null
  total_runs_count: number | null
  full_dx_km: number | null
  km_this_month: number | null
  current_streak: number | null
  longest_streak: number | null
  achievements: RawAchievement[] | null
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

function mapPublicProfile(raw: RawPublicProfile): PublicProfile {
  return {
    id: raw.id,
    first_name: raw.first_name,
    last_name: raw.last_name,
    avatar_url: raw.avatar ?? null,
    is_guest: raw.is_guest,
    registered_at: raw.registered_at ?? null,
    lock_reason: raw.lock_reason,
    missing_fields: raw.missing_fields,
    rating: raw.rating,
    finished_count: raw.rating,
    first_run_date: raw.first_run_date ?? null,
    total_runs_count: raw.total_runs_count,
    full_dx_km: raw.full_dx_km,
    km_this_month: raw.km_this_month,
    current_streak: raw.current_streak,
    longest_streak: raw.longest_streak,
    achievements: raw.achievements ? raw.achievements.map(mapAchievement) : null,
  }
}

function mapAchievement(raw: RawAchievement): Achievement {
  return {
    threshold: raw.threshold,
    reached: raw.reached,
    reached_at: raw.reached_at ?? null,
    event_id: raw.event_id ?? null,
    event_title: raw.event_title ?? null,
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

  historyPage: async (
    id: number | string,
    page: number,
    pageSize = 20,
  ): Promise<Paginated<ParticipationEntry>> => {
    const raw = await api.get<Paginated<RawHistoryItem>>(`/users/${id}/history`, {
      query: { page, page_size: pageSize },
    })
    return { ...raw, items: await Promise.all(raw.items.map(mapHistoryItem)) }
  },

  exportMe: () => api.get<AccountExport>('/users/me/export'),

  deleteMe: (password: string) =>
    api.del<{ message?: string }>('/users/me', { password }),
}
