import { api } from './client'

export interface AttentionCounts {
  tickets: number
  claims: number
  moderation: number
}

export const staffApi = {
  attentionCounts: () => api.get<AttentionCounts>('/staff/attention-counts'),
}
