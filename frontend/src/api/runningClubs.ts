import { api } from './client'

export interface RunningClubResult {
  id: number
  title: string
  city: string | null
}

export const runningClubsApi = {
  search: (q: string, limit = 8) =>
    api.get<RunningClubResult[]>('/running-clubs/search', { query: { q, limit }, auth: false }),
}
