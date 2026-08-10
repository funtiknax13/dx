import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { supportApi } from '../api/support'
import { ApiError } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { FormError, FormSuccess } from '../components/AuthShell'
import { formatDate } from '../lib/format'
import { IconMail, IconSpark } from '../components/ui/icons'

export function SupportPage() {
  const { isAuthenticated } = useAuth()
  const [body, setBody] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const {
    data: tickets,
    loading: ticketsLoading,
    reload,
  } = useAsync(
    () => (isAuthenticated ? supportApi.myTickets() : Promise.resolve([])),
    [isAuthenticated],
  )

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await supportApi.createTicket({ body })
      setBody('')
      setSuccess(true)
      reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить обращение')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="container-page max-w-2xl py-10 sm:py-14">
      <span className="eyebrow text-signal">
        <IconMail width={16} height={16} /> Поддержка
      </span>
      <h1 className="mt-3 font-display text-3xl sm:text-4xl">Связаться с нами</h1>
      <p className="mt-3 text-ink-600">
        Вопрос по регистрации, событию или результату — напишите, организаторы ответят здесь же.
      </p>

      {isAuthenticated ? (
        <form onSubmit={submit} className="card mt-8 space-y-5 p-6 sm:p-8">
          <FormError message={error} />
          {success && <FormSuccess message="Обращение отправлено — ответ придёт сюда." />}
          <div>
            <label htmlFor="body" className="field-label">
              Сообщение *
            </label>
            <textarea
              id="body"
              rows={5}
              required
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="field"
            />
          </div>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? 'Отправка…' : 'Отправить'}
          </button>
        </form>
      ) : (
        <div className="mt-8">
          <StatePanel
            title="Войдите, чтобы написать в поддержку"
            description="Обращения доступны только зарегистрированным участникам — так мы сможем ответить вам прямо на сайте."
            icon={<IconMail />}
            action={
              <div className="flex gap-3">
                <Link to="/login" state={{ from: '/support' }} className="btn-primary">
                  Войти
                </Link>
                <Link to="/register" className="btn-ghost">
                  Зарегистрироваться
                </Link>
              </div>
            }
          />
        </div>
      )}

      {isAuthenticated && (
        <div className="mt-10">
          <h2 className="font-display text-xl">Мои обращения</h2>
          {ticketsLoading ? (
            <PageLoader />
          ) : !tickets || tickets.length === 0 ? (
            <p className="mt-3 text-sm text-ink-600">Обращений пока нет.</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {tickets.map((t) => (
                <li key={t.id}>
                  <Link
                    to={`/support/tickets/${t.id}`}
                    className="card flex items-center justify-between gap-4 p-4 transition hover:border-ink/25"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={`chip shrink-0 ${
                            t.status === 'open'
                              ? 'bg-signal/12 text-signal-600'
                              : 'bg-ink text-paper'
                          }`}
                        >
                          {t.status === 'open' ? 'Открыт' : 'Закрыт'}
                        </span>
                        <p className="truncate text-sm font-semibold text-ink">{t.preview}</p>
                      </div>
                      <p className="mt-1.5 font-mono text-[0.7rem] uppercase tracking-[0.12em] text-clay">
                        {formatDate(t.created_at)}
                      </p>
                    </div>
                    {t.has_unread && (
                      <span className="chip shrink-0 bg-signal text-white">
                        <IconSpark width={12} height={12} /> новое
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
