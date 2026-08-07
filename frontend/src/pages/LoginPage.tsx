import { useCallback, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { useCaptchaConfig } from '../api/captcha'
import { AuthShell, FormError } from '../components/AuthShell'
import { Field, PasswordField } from '../components/ui/Field'
import { SmartCaptcha } from '../components/ui/SmartCaptcha'
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
  // The captcha only appears once the server starts asking for it (429/428
  // after repeated failures) — a normal first login never sees it.
  const [captchaRequired, setCaptchaRequired] = useState(false)
  const [captchaToken, setCaptchaToken] = useState('')
  const captcha = useCaptchaConfig()

  const handleToken = useCallback((token: string) => {
    setCaptchaToken(token)
    setError(null)
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login({ email, password, captcha_token: captchaToken || undefined })
      navigate(from, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 428) {
        setCaptchaRequired(true)
        setError('Подтвердите, что вы не робот, и повторите вход.')
      } else {
        setError(
          err instanceof ApiError
            ? err.status === 401 || err.status === 400
              ? 'Неверный email или пароль'
              : err.message
            : 'Не удалось войти',
        )
      }
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
        {captchaRequired && captcha?.enabled && captcha.client_key && (
          <SmartCaptcha sitekey={captcha.client_key} onToken={handleToken} />
        )}
        <button
          type="submit"
          disabled={loading || (captchaRequired && !captchaToken)}
          className="btn-primary btn-lg w-full"
        >
          {loading ? <Spinner className="h-5 w-5" /> : 'Войти'}
        </button>
      </form>
    </AuthShell>
  )
}
