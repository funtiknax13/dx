import { api } from './client'
import type { RatingEntry, RatingPeriod, StatsLockReason } from '../types'

interface RawRatingItem {
  rank: number
  runner_id: number
  first_name: string
  last_name: string
  avatar?: string | null
  finished_count: number
}

interface RawRatingResponse {
  period: string
  entries: RawRatingItem[]
  me: RawRatingItem | null
  lock_reason: StatsLockReason
  missing_fields: string[]
}

function mapItem(e: RawRatingItem): RatingEntry {
  return {
    rank: e.rank,
    user_id: e.runner_id,
    first_name: e.first_name,
    last_name: e.last_name,
    avatar_url: e.avatar ?? null,
    city: null,
    finished_count: e.finished_count,
    score: e.finished_count,
  }
}

export const ratingApi = {
  list: async (
    period: RatingPeriod = 'all',
  ): Promise<{
    entries: RatingEntry[]
    me: RatingEntry | null
    lockReason: StatsLockReason
    missingFields: string[]
  }> => {
    // No `auth: false` here — the request client already attaches the token
    // when a session exists, and the endpoint stays public either way; being
    // logged in just adds a personalized `me` row when outside the top N.
    const res = await api.get<RawRatingResponse>('/rating', { query: { period } })
    return {
      entries: res.entries.map(mapItem),
      me: res.me ? mapItem(res.me) : null,
      lockReason: res.lock_reason,
      missingFields: res.missing_fields,
    }
  },
}
