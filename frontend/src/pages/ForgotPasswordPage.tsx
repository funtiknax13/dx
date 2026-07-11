import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthShell, FormError } from '../components/AuthShell'
import { Field } from '../components/ui/Field'
import { Spinner } from '../components/ui/Spinner'
import { IconMail } from '../components/ui/icons'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await authApi.forgotPassword(email.trim())
      setSent(true)
    } catch (err) {
      // Do not leak whether the account exists — show success-style message unless it's a server error.
      if (err instanceof ApiError && err.status >= 500) {
        setError('Сервис временно недоступен. Попробуйте позже.')
      } else {
        setSent(true)
      }
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <AuthShell
        title="Проверьте почту"
        footer={
          <Link to="/login" className="font-semibold text-signal hover:underline">
            Вернуться ко входу
          </Link>
        }
      >
        <div className="rounded-xl2 border border-ink/[0.08] bg-white p-6 text-center shadow-card">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-ink text-volt">
            <IconMail width={30} height={30} />
          </div>
          <p className="mt-5 text-ink-700">
            Если аккаунт с адресом <span className="font-semibold">{email}</span> существует, мы
            отправили на него ссылку для сброса пароля.
          </p>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Сброс пароля"
      subtitle="Введите email — пришлём ссылку для создания нового пароля."
      footer={
        <span>
          Вспомнили пароль?{' '}
          <Link to="/login" className="font-semibold text-signal hover:underline">
            Войти
          </Link>
        </span>
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
        <button type="submit" disabled={loading} className="btn-primary btn-lg w-full">
          {loading ? <Spinner className="h-5 w-5" /> : 'Отправить ссылку'}
        </button>
      </form>
    </AuthShell>
  )
}
