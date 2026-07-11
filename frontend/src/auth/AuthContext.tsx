import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { authApi } from '../api/auth'
import { usersApi } from '../api/users'
import { tokenStore } from '../api/tokens'
import type { LoginPayload, User } from '../types'

interface AuthState {
  user: User | null
  loading: boolean
  isAuthenticated: boolean
  login: (payload: LoginPayload) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  setUser: (u: User) => void
}

const AuthContext = createContext<AuthState | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const loadUser = useCallback(async () => {
    if (!tokenStore.hasSession) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await usersApi.me()
      setUser(me)
    } catch {
      tokenStore.clear()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadUser()
  }, [loadUser])

  // React to forced logout dispatched by the API client on unrecoverable 401.
  useEffect(() => {
    const onUnauthorized = () => {
      tokenStore.clear()
      setUser(null)
    }
    window.addEventListener('dh:unauthorized', onUnauthorized)
    return () => window.removeEventListener('dh:unauthorized', onUnauthorized)
  }, [])

  const login = useCallback(async (payload: LoginPayload) => {
    const tokens = await authApi.login(payload)
    tokenStore.set(tokens)
    const me = await usersApi.me()
    setUser(me)
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    if (!tokenStore.hasSession) return
    const me = await usersApi.me()
    setUser(me)
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user),
      login,
      logout,
      refreshUser,
      setUser,
    }),
    [user, loading, login, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
