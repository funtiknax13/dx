import { api } from './client'
import type { EventSignupState, MySignupEntry, Signup } from '../types'

/** A past event the runner signed up to, where they can still self-report a
 * result (or one is pending). */
export interface AwaitingResultEntry {
  /** Null for a group added via the "Я бегал(а)" deep link — no signup behind it. */
  signup_id: number | null
  group_id: number
  group_name: string
  location: string
  event_id: number
  event_title: string
  event_date: string
  start_time: string | null
  has_result: boolean
  moderation_status: 'pending' | 'approved' | 'rejected' | null
}

export const signupsApi = {
  create: (groupId: number | string) => api.post<Signup>(`/groups/${groupId}/signups`),
  remove: (signupId: number | string) => api.del<void>(`/signups/${signupId}`),
  eventState: (eventId: number | string) =>
    api.get<EventSignupState>(`/events/${eventId}/signups/me`),
  mine: () => api.get<MySignupEntry[]>('/users/me/signups'),
  /** `includeGroupId` adds that (started) group even without a signup — the
   * "Я бегал(а)" deep link from a group page. */
  awaitingResults: (includeGroupId?: number | null) =>
    api.get<AwaitingResultEntry[]>('/users/me/signups/awaiting-result', {
      query: includeGroupId ? { include_group_id: includeGroupId } : undefined,
    }),
}
