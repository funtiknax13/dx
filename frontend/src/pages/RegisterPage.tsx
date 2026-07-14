import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthShell, FormError } from '../components/AuthShell'
import { Field, PasswordField } from '../components/ui/Field'
import { Spinner } from '../components/ui/Spinner'

export function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    confirm: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const validate = () => {
    const errs: Record<string, string> = {}
    if (!form.first_name.trim()) errs.first_name = 'Укажите имя'
    if (!form.last_name.trim()) errs.last_name = 'Укажите фамилию'
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) errs.email = 'Некорректный email'
    if (form.password.length < 8) errs.password = 'Минимум 8 символов'
    if (form.password !== form.confirm) errs.confirm = 'Пароли не совпадают'
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
      })
      navigate(`/verify-email?email=${encodeURIComponent(form.email.trim())}`, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 409
            ? 'Пользователь с таким email уже существует'
            : err.message
          : 'Не удалось зарегистрироваться',
      )
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
            value={form.first_name}
            onChange={set('first_name')}
            error={fieldErrors.first_name}
            required
          />
          <Field
            label="Фамилия"
            name="last_name"
            autoComplete="family-name"
            placeholder="Петров"
            value={form.last_name}
            onChange={set('last_name')}
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
          placeholder="Минимум 8 символов"
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
        <button type="submit" disabled={loading} className="btn-primary btn-lg w-full">
          {loading ? <Spinner className="h-5 w-5" /> : 'Зарегистрироваться'}
        </button>
        <p className="text-center text-xs text-clay">
          Регистрируясь, вы соглашаетесь с правилами сообщества DАЙ ХАРD
        </p>
      </form>
    </AuthShell>
  )
}
