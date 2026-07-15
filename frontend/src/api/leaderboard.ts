import { api } from './client'
import type { LeaderboardEntry, LeaderboardMetric, RatingPeriod } from '../types'

interface RawLeaderboardItem {
  rank: number
  runner_id: number
  first_name: string
  last_name: string
  avatar?: string | null
  value: number
}

interface RawLeaderboardResponse {
  metric: string
  period: string
  entries: RawLeaderboardItem[]
}

export const leaderboardApi = {
  list: async (
    metric: LeaderboardMetric,
    period: RatingPeriod = 'all',
  ): Promise<LeaderboardEntry[]> => {
    const res = await api.get<RawLeaderboardResponse>('/leaderboard', {
      query: { metric, period },
      auth: false,
    })
    return res.entries.map((e) => ({
      rank: e.rank,
      user_id: e.runner_id,
      first_name: e.first_name,
      last_name: e.last_name,
      avatar_url: e.avatar ?? null,
      value: e.value,
    }))
  },
}
