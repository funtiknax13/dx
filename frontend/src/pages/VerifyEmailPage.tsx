import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthShell } from '../components/AuthShell'
import { Spinner } from '../components/ui/Spinner'
import { IconCheck, IconMail, IconX } from '../components/ui/icons'

type Status = 'idle' | 'verifying' | 'success' | 'error'

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const email = params.get('email')
  const [status, setStatus] = useState<Status>(token ? 'verifying' : 'idle')
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    let active = true
    authApi
      .verifyEmail(token)
      .then((res) => {
        if (!active) return
        setStatus('success')
        setMessage(res.message ?? null)
      })
      .catch((err) => {
        if (!active) return
        setStatus('error')
        setMessage(
          err instanceof ApiError ? err.message : 'Ссылка недействительна или устарела',
        )
      })
    return () => {
      active = false
    }
  }, [token])

  // Post-registration "check your email" screen
  if (status === 'idle') {
    return (
      <AuthShell
        title="Проверьте почту"
        subtitle="Мы отправили письмо со ссылкой для подтверждения аккаунта."
        footer={
          <span>
            Уже подтвердили?{' '}
            <Link to="/login" className="font-semibold text-signal hover:underline">
              Войти
            </Link>
          </span>
        }
      >
        <div className="rounded-xl2 border border-ink/[0.08] bg-white p-6 text-center shadow-card">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-ink text-volt">
            <IconMail width={30} height={30} />
          </div>
          <p className="mt-5 text-ink-700">
            {email ? (
              <>
                Письмо отправлено на{' '}
                <span className="font-semibold text-ink">{email}</span>.
              </>
            ) : (
              'Письмо с подтверждением отправлено на указанный адрес.'
            )}
          </p>
          <p className="mt-2 text-sm text-clay">
            Перейдите по ссылке из письма, чтобы активировать аккаунт. Не пришло — проверьте папку
            «Спам».
          </p>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title={
        status === 'success'
          ? 'Email подтверждён'
          : status === 'error'
            ? 'Не удалось подтвердить'
            : 'Подтверждаем email'
      }
    >
      <div className="rounded-xl2 border border-ink/[0.08] bg-white p-8 text-center shadow-card">
        {status === 'verifying' && (
          <>
            <Spinner className="h-8 w-8 text-signal" />
            <p className="mt-4 text-ink-600">Проверяем ссылку…</p>
          </>
        )}
        {status === 'success' && (
          <>
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-ink text-volt">
              <IconCheck width={32} height={32} />
            </div>
            <p className="mt-5 text-ink-700">
              {message ?? 'Ваш email подтверждён. Теперь можно войти в аккаунт.'}
            </p>
            <Link to="/login" className="btn-primary btn-lg mt-6 w-full">
              Перейти ко входу
            </Link>
          </>
        )}
        {status === 'error' && (
          <>
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-signal text-white">
              <IconX width={32} height={32} />
            </div>
            <p className="mt-5 text-ink-700">{message}</p>
            <Link to="/register" className="btn-ghost btn-lg mt-6 w-full">
              Зарегистрироваться заново
            </Link>
          </>
        )}
      </div>
    </AuthShell>
  )
}
