import { useCallback, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { useCaptchaConfig } from '../api/captcha'
import { AuthShell, FormError } from '../components/AuthShell'
import { Field, PasswordField } from '../components/ui/Field'
import { Altcha } from '../components/ui/Altcha'
import { Spinner } from '../components/ui/Spinner'
import {
  NAME_MAX_LENGTH,
  PASSWORD_HINT,
  capitalizeFirst,
  emailError,
  nameError,
  passwordError,
} from '../lib/validation'

export function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    confirm: '',
  })
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [captchaRequired, setCaptchaRequired] = useState(false)
  const [captchaToken, setCaptchaToken] = useState('')
  // Bumped to remount the widget for a fresh single-use token after a failure.
  const [captchaNonce, setCaptchaNonce] = useState(0)
  const captcha = useCaptchaConfig()

  // Only stores the token — clearing the error here would wipe a real error
  // when the widget's async re-solve fires right after a failed attempt.
  const handleToken = useCallback((token: string) => {
    setCaptchaToken(token)
  }, [])

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  // Names are capitalised as you type (first letter auto-uppercased).
  const setName = (k: 'first_name' | 'last_name') => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: capitalizeFirst(e.target.value) }))

  const validate = () => {
    const errs: Record<string, string> = {}
    const firstErr = nameError(form.first_name, 'Укажите имя')
    if (firstErr) errs.first_name = firstErr
    const lastErr = nameError(form.last_name, 'Укажите фамилию')
    if (lastErr) errs.last_name = lastErr
    const emailErr = emailError(form.email)
    if (emailErr) errs.email = emailErr
    const passErr = passwordError(form.password)
    if (passErr) errs.password = passErr
    if (form.password !== form.confirm) errs.confirm = 'Пароли не совпадают'
    if (!consent) errs.consent = 'Необходимо согласие на обработку персональных данных'
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!validate()) return
    setLoading(true)
    try {
      await authApi.register({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        password: form.password,
        accept_privacy_policy: consent,
        captcha_token: captchaToken || undefined,
      })
      navigate(`/verify-email?email=${encodeURIComponent(form.email.trim())}`, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 428) {
        setCaptchaRequired(true)
        setError('Подтвердите, что вы не робот, и повторите отправку.')
      } else {
        setError(
          err instanceof ApiError ? err.message : 'Не удалось зарегистрироваться',
        )
      }
      // Spent token — refresh the widget for the next attempt.
      setCaptchaToken('')
      setCaptchaNonce((n) => n + 1)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      title="Создать аккаунт"
      subtitle="Имя, фамилия и email — остальное можно заполнить в профиле позже."
      footer={
        <span>
          Уже с нами?{' '}
          <Link to="/login" className="font-semibold text-signal hover:underline">
            Войти
          </Link>
        </span>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormError message={error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Имя"
            name="first_name"
            autoComplete="given-name"
            placeholder="Иван"
            maxLength={NAME_MAX_LENGTH}
            value={form.first_name}
            onChange={setName('first_name')}
            error={fieldErrors.first_name}
            required
          />
          <Field
            label="Фамилия"
            name="last_name"
            autoComplete="family-name"
            placeholder="Петров"
            maxLength={NAME_MAX_LENGTH}
            value={form.last_name}
            onChange={setName('last_name')}
            error={fieldErrors.last_name}
            required
          />
        </div>
        <Field
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={form.email}
          onChange={set('email')}
          error={fieldErrors.email}
          required
        />
        <PasswordField
          label="Пароль"
          name="password"
          autoComplete="new-password"
          placeholder={PASSWORD_HINT}
          value={form.password}
          onChange={set('password')}
          error={fieldErrors.password}
          required
        />
        <PasswordField
          label="Повторите пароль"
          name="confirm"
          autoComplete="new-password"
          placeholder="••••••••"
          value={form.confirm}
          onChange={set('confirm')}
          error={fieldErrors.confirm}
          required
        />
        <div>
          <label className="flex items-start gap-2.5 text-sm text-ink-600">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => {
                setConsent(e.target.checked)
                setFieldErrors((f) => ({ ...f, consent: '' }))
              }}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-ink/30 text-signal focus:ring-signal/40"
            />
            <span>
              Я согласен(на) с{' '}
              <Link
                to="/privacy-policy"
                target="_blank"
                className="font-semibold text-signal hover:underline"
              >
                политикой обработки персональных данных
              </Link>{' '}
              и даю согласие на обработку своих персональных данных
            </span>
          </label>
          {fieldErrors.consent && (
            <p className="mt-1.5 text-xs text-danger-600">{fieldErrors.consent}</p>
          )}
        </div>
        {captchaRequired && captcha?.enabled && (
          <Altcha key={captchaNonce} onToken={handleToken} />
        )}
        <button
          type="submit"
          disabled={loading || (captchaRequired && !captchaToken)}
          className="btn-primary btn-lg w-full"
        >
          {loading ? <Spinner className="h-5 w-5" /> : 'Зарегистрироваться'}
        </button>
      </form>
    </AuthShell>
  )
}
