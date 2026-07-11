import { api } from './client'
import type { RatingEntry, RatingPeriod } from '../types'

interface RawRatingItem {
  runner_id: number
  first_name: string
  last_name: string
  avatar?: string | null
  finished_count: number
}

interface RawRatingResponse {
  period: string
  entries: RawRatingItem[]
}

export const ratingApi = {
  list: async (period: RatingPeriod = 'all'): Promise<RatingEntry[]> => {
    const res = await api.get<RawRatingResponse>('/rating', { query: { period }, auth: false })
    return res.entries.map((e, i) => ({
      rank: i + 1,
      user_id: e.runner_id,
      first_name: e.first_name,
      last_name: e.last_name,
      avatar_url: e.avatar ?? null,
      city: null,
      finished_count: e.finished_count,
      score: e.finished_count,
    }))
  },
}
