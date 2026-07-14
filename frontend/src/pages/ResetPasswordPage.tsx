import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthShell, FormError, FormSuccess } from '../components/AuthShell'
import { PasswordField } from '../components/ui/Field'
import { Spinner } from '../components/ui/Spinner'

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const navigate = useNavigate()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError('Пароль должен содержать минимум 8 символов')
      return
    }
    if (password !== confirm) {
      setError('Пароли не совпадают')
      return
    }
    if (!token) {
      setError('Отсутствует токен сброса. Откройте ссылку из письма ещё раз.')
      return
    }
    setLoading(true)
    try {
      await authApi.resetPassword(token, password)
      setDone(true)
      setTimeout(() => navigate('/login', { replace: true }), 1800)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Не удалось сбросить пароль. Ссылка могла устареть.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      title="Новый пароль"
      subtitle="Придумайте новый пароль для входа в аккаунт."
      footer={
        <Link to="/login" className="font-semibold text-signal hover:underline">
          Вернуться ко входу
        </Link>
      }
    >
      {!token && (
        <div className="mb-4">
          <FormError message="Ссылка недействительна: отсутствует токен. Запросите сброс заново." />
        </div>
      )}
      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormError message={error} />
        <FormSuccess message={done ? 'Пароль обновлён. Перенаправляем ко входу…' : null} />
        <PasswordField
          label="Новый пароль"
          name="password"
          autoComplete="new-password"
          placeholder="Минимум 8 символов"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <PasswordField
          label="Повторите пароль"
          name="confirm"
          autoComplete="new-password"
          placeholder="••••••••"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
        <button type="submit" disabled={loading || done} className="btn-primary btn-lg w-full">
          {loading ? <Spinner className="h-5 w-5" /> : 'Сохранить пароль'}
        </button>
      </form>
    </AuthShell>
  )
}
