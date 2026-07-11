import type { Tokens } from '../types'

// MVP simplification (per plan): JWT access+refresh stored in localStorage.
const ACCESS_KEY = 'dh.access'
const REFRESH_KEY = 'dh.refresh'

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(tokens: Tokens) {
    localStorage.setItem(ACCESS_KEY, tokens.access_token)
    if (tokens.refresh_token) localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
  get hasSession() {
    return Boolean(localStorage.getItem(ACCESS_KEY))
  },
}
