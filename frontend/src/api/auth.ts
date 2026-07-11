import { api } from './client'
import type { LoginPayload, RegisterPayload, Tokens, User } from '../types'

export const authApi = {
  register: (payload: RegisterPayload) =>
    api.post<{ message?: string; user?: User }>('/auth/register', payload, { auth: false }),

  verifyEmail: (token: string) =>
    api.get<{ message?: string }>('/auth/verify-email', { query: { token }, auth: false }),

  login: (payload: LoginPayload) => api.post<Tokens>('/auth/login', payload, { auth: false }),

  refresh: (refresh_token: string) =>
    api.post<Tokens>('/auth/refresh', { refresh_token }, { auth: false }),

  forgotPassword: (email: string) =>
    api.post<{ message?: string }>('/auth/forgot-password', { email }, { auth: false }),

  resetPassword: (token: string, new_password: string) =>
    api.post<{ message?: string }>('/auth/reset-password', { token, new_password }, { auth: false }),
}
