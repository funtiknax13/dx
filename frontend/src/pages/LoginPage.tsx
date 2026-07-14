import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { AuthShell, FormError } from '../components/AuthShell'
import { Field, PasswordField } from '../components/ui/Field'
import { Spinner } from '../components/ui/Spinner'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/events'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login({ email, password })
      navigate(from, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 401 || err.status === 400
            ? 'Неверный email или пароль'
            : err.message
          : 'Не удалось войти',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      title="С возвращением"
      subtitle="Войдите, чтобы записываться на группы и вести свой протокол."
      footer={
        <div className="flex flex-col gap-2">
          <span>
            Нет аккаунта?{' '}
            <Link to="/register" className="font-semibold text-signal hover:underline">
              Зарегистрироваться
            </Link>
          </span>
          <Link to="/forgot-password" className="text-clay hover:text-ink">
            Забыли пароль?
          </Link>
        </div>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormError message={error} />
        <Field
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <PasswordField
          label="Пароль"
          name="password"
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button type="submit" disabled={loading} className="btn-primary btn-lg w-full">
          {loading ? <Spinner className="h-5 w-5" /> : 'Войти'}
        </button>
      </form>
    </AuthShell>
  )
}
