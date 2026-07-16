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
  me: RawLeaderboardItem | null
}

function mapItem(e: RawLeaderboardItem): LeaderboardEntry {
  return {
    rank: e.rank,
    user_id: e.runner_id,
    first_name: e.first_name,
    last_name: e.last_name,
    avatar_url: e.avatar ?? null,
    value: e.value,
  }
}

export const leaderboardApi = {
  list: async (
    metric: LeaderboardMetric,
    period: RatingPeriod = 'all',
  ): Promise<{ entries: LeaderboardEntry[]; me: LeaderboardEntry | null }> => {
    // No `auth: false` — see api/rating.ts for why.
    const res = await api.get<RawLeaderboardResponse>('/leaderboard', { query: { metric, period } })
    return { entries: res.entries.map(mapItem), me: res.me ? mapItem(res.me) : null }
  },
}
