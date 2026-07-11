import { api } from './client'
import type { Signup } from '../types'

export const signupsApi = {
  create: (groupId: number | string) => api.post<Signup>(`/groups/${groupId}/signups`),
  remove: (signupId: number | string) => api.del<void>(`/signups/${signupId}`),
}
