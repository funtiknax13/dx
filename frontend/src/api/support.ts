import { api } from './client'
import type { SupportTicketDetail, SupportTicketSummary } from '../types'

export const supportApi = {
  createTicket: (payload: { body: string; guest_name?: string; guest_contact?: string }) =>
    api.post<SupportTicketSummary>('/support/tickets', payload),

  myTickets: () => api.get<SupportTicketSummary[]>('/support/tickets'),

  unreadCount: () => api.get<{ count: number }>('/support/tickets/unread-count'),

  ticket: (id: number) => api.get<SupportTicketDetail>(`/support/tickets/${id}`),

  reply: (id: number, body: string) =>
    api.post<SupportTicketDetail>(`/support/tickets/${id}/messages`, { body }),
}
