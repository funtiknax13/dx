import { tokenStore } from './tokens'
import type { Tokens } from '../types'

const API_URL = (import.meta.env.VITE_API_URL ?? '/api/v1').replace(/\/$/, '')
// The backend already returns root-relative paths that include their own
// "/media/..." prefix (see MEDIA_URL setting in backend/.env.example), so
// resolving them just needs the API's origin, not a second "/media" base —
// concatenating VITE_MEDIA_URL here would double that segment.
export const API_ORIGIN = API_URL.replace(/\/api\/v\d+$/, '')
export const MEDIA_URL = (import.meta.env.VITE_MEDIA_URL ?? '/media').replace(/\/$/, '')

/** Resolve a (possibly relative) media path returned by the API. */
export function media(path?: string | null): string | undefined {
  if (!path) return undefined
  if (/^https?:\/\//i.test(path)) return path
  return `${API_ORIGIN}${path.startsWith('/') ? path : `/${path}`}`
}

/**
 * Single-sign-on link into the server-rendered admin-tools mini-app (organizer
 * and admin only) — exchanges the current access token for the session cookie
 * admin-tools reads, so there's no second login. If the token happens to have
 * just expired, admin-tools falls back to its own email/password login screen.
 */
export function adminToolsUrl(): string {
  const token = tokenStore.access ?? ''
  return `${API_ORIGIN}/admin-tools/sso?token=${encodeURIComponent(token)}`
}

export class ApiError extends Error {
  status: number
  data: unknown
  constructor(status: number, message: string, data?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

type Body = object | FormData | undefined

interface RequestOptions {
  method?: string
  body?: Body
  auth?: boolean // attach access token (default: true when a session exists)
  query?: Record<string, string | number | boolean | undefined>
  signal?: AbortSignal
}

let refreshInFlight: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  const refresh = tokenStore.refresh
  if (!refresh) return false
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })
      .then(async (res) => {
        if (!res.ok) return false
        const data = (await res.json()) as Tokens
        tokenStore.set(data)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_URL}${path.startsWith('/') ? path : `/${path}`}`, window.location.origin)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v))
    }
  }
  // API_URL may be absolute; if so URL() ignores the base — reconstruct properly.
  return /^https?:\/\//i.test(API_URL)
    ? `${API_URL}${path.startsWith('/') ? path : `/${path}`}${query ? toQuery(query) : ''}`
    : url.pathname + url.search
}

function toQuery(query: RequestOptions['query']): string {
  if (!query) return ''
  const parts = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

async function raw<T>(path: string, opts: RequestOptions, retry = true): Promise<T> {
  const { method = 'GET', body, auth, query, signal } = opts
  const headers: Record<string, string> = {}
  const useAuth = auth ?? tokenStore.hasSession
  if (useAuth && tokenStore.access) {
    headers['Authorization'] = `Bearer ${tokenStore.access}`
  }

  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const res = await fetch(buildUrl(path, query), { method, headers, body: payload, signal })

  if (res.status === 401 && retry && useAuth && tokenStore.refresh) {
    const ok = await tryRefresh()
    if (ok) return raw<T>(path, opts, false)
    tokenStore.clear()
    window.dispatchEvent(new CustomEvent('dh:unauthorized'))
  }

  if (!res.ok) {
    let data: unknown
    let message = `Ошибка ${res.status}`
    try {
      data = await res.json()
      const detail = (data as { detail?: unknown; message?: unknown })?.detail
      if (typeof detail === 'string') message = detail
      else if (Array.isArray(detail) && detail[0]?.msg) message = String(detail[0].msg)
      else if (typeof (data as { message?: unknown })?.message === 'string')
        message = String((data as { message: string }).message)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message, data)
  }

  if (res.status === 204) return undefined as T
  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) return (await res.json()) as T
  return (await res.text()) as unknown as T
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    raw<T>(path, { ...opts, method: 'GET' }),
  post: <T>(path: string, body?: Body, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    raw<T>(path, { ...opts, method: 'POST', body }),
  patch: <T>(path: string, body?: Body, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    raw<T>(path, { ...opts, method: 'PATCH', body }),
  del: <T>(path: string, body?: Body, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    raw<T>(path, { ...opts, method: 'DELETE', body }),
  apiUrl: API_URL,
}
