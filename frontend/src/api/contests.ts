import { api } from './client'
import type {
  ContestDetail,
  ContestEntriesResponse,
  ContestSummary,
  MyContestEntry,
} from '../types'

export const contestsApi = {
  list: (): Promise<ContestSummary[]> => api.get<ContestSummary[]>('/contests'),

  detail: (id: number | string): Promise<ContestDetail> =>
    api.get<ContestDetail>(`/contests/${id}`),

  myEntry: (id: number | string): Promise<MyContestEntry | null> =>
    api.get<MyContestEntry | null>(`/contests/${id}/my-entry`),

  // `values` keys are "field_<id>" — a string for text/number/url fields, a
  // File for image/gpx ones not being replaced this submit (omit the key
  // entirely to keep whatever file is already on record, see the backend).
  submit: (
    id: number | string,
    values: Record<string, string | File>,
  ): Promise<MyContestEntry> => {
    const form = new FormData()
    for (const [key, value] of Object.entries(values)) form.append(key, value)
    return api.post<MyContestEntry>(`/contests/${id}/entries`, form)
  },

  entries: (id: number | string): Promise<ContestEntriesResponse> =>
    api.get<ContestEntriesResponse>(`/contests/${id}/entries`),

  vote: (contestId: number | string, entryId: number): Promise<void> =>
    api.post<void>(`/contests/${contestId}/entries/${entryId}/vote`),
}
