import { api } from './client'
import { mapRouteMap, type RawRouteMap } from '../lib/routeMap'
import type {
  ContestDetail,
  ContestEntriesResponse,
  ContestSummary,
  MyContestEntry,
  RouteMap,
} from '../types'

export const contestsApi = {
  list: (): Promise<ContestSummary[]> => api.get<ContestSummary[]>('/contests'),

  detail: (id: number | string): Promise<ContestDetail> =>
    api.get<ContestDetail>(`/contests/${id}`),

  myEntries: (id: number | string): Promise<MyContestEntry[]> =>
    api.get<MyContestEntry[]>(`/contests/${id}/my-entries`),

  // `values` keys are "field_<id>" — a string for text/number/url/
  // multi_select fields, a File (or File[], for image fields that take
  // several photos) for image/gpx ones not being replaced this submit
  // (omit the key entirely to keep whatever's already on record, see the
  // backend). `entryId` targets an existing entry to edit; omitted creates
  // a new one (subject to Contest.max_entries_per_runner).
  submit: (
    id: number | string,
    values: Record<string, string | File | File[]>,
    entryId?: number,
  ): Promise<MyContestEntry> => {
    const form = new FormData()
    if (entryId != null) form.append('entry_id', String(entryId))
    for (const [key, value] of Object.entries(values)) {
      if (Array.isArray(value)) {
        for (const file of value) form.append(key, file)
      } else {
        form.append(key, value)
      }
    }
    return api.post<MyContestEntry>(`/contests/${id}/entries`, form)
  },

  entries: (id: number | string): Promise<ContestEntriesResponse> =>
    api.get<ContestEntriesResponse>(`/contests/${id}/entries`),

  vote: (contestId: number | string, entryId: number): Promise<void> =>
    api.post<void>(`/contests/${contestId}/entries/${entryId}/vote`),

  routeMap: async (
    contestId: number | string,
    entryId: number,
    fieldId: number,
  ): Promise<RouteMap> =>
    mapRouteMap(
      await api.get<RawRouteMap>(
        `/contests/${contestId}/entries/${entryId}/values/${fieldId}/route-map`,
      ),
    ),
}
