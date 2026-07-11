import { api } from './client'
import type { EventSignupState, MySignupEntry, Signup } from '../types'

export const signupsApi = {
  create: (groupId: number | string) => api.post<Signup>(`/groups/${groupId}/signups`),
  remove: (signupId: number | string) => api.del<void>(`/signups/${signupId}`),
  eventState: (eventId: number | string) =>
    api.get<EventSignupState>(`/events/${eventId}/signups/me`),
  mine: () => api.get<MySignupEntry[]>('/users/me/signups'),
}
