import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { supportApi } from '../api/support'
import { ApiError } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { FormError } from '../components/AuthShell'
import { formatDate } from '../lib/format'
import { IconMail, IconX } from '../components/ui/icons'

export function SupportTicketPage() {
  const { id } = useParams<{ id: string }>()
  const ticketId = Number(id)
  const { data: ticket, loading, error, setData } = useAsync(
    () => supportApi.ticket(ticketId),
    [ticketId],
  )
  const [body, setBody] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!body.trim()) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      const updated = await supportApi.reply(ticketId, body)
      setData(updated)
      setBody('')
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Не удалось отправить сообщение')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <PageLoader />

  if (error || !ticket) {
    return (
      <div className="container-page py-16">
        <StatePanel
          title="Обращение не найдено"
          description={error ?? undefined}
          icon={<IconX />}
          action={
            <Link to="/support" className="btn-ink">
              К моим обращениям
            </Link>
          }
        />
      </div>
    )
  }

  return (
    <div className="container-page max-w-2xl py-10 sm:py-14">
      <span className="eyebrow text-signal">
        <IconMail width={16} height={16} /> Обращение #{ticket.id}
      </span>
      <div className="mt-3 flex items-center justify-between gap-4">
        <h1 className="font-display text-3xl sm:text-4xl">
          {ticket.status === 'open' ? 'Открыто' : 'Закрыто'}
        </h1>
        <Link to="/support" className="btn-ghost btn-sm">
          Все обращения
        </Link>
      </div>

      <div className="mt-8 space-y-4">
        {ticket.messages.map((m) => (
          <div
            key={m.id}
            className={`card p-4 ${m.is_staff ? 'border-signal/30 bg-signal-wash/30' : ''}`}
          >
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-600">
              {m.is_staff ? 'Поддержка' : 'Вы'} · {formatDate(m.created_at)}
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-ink">{m.body}</p>
          </div>
        ))}
      </div>

      <form onSubmit={submit} className="card mt-6 space-y-4 p-6">
        <FormError message={submitError} />
        <div>
          <label htmlFor="reply" className="field-label">
            Ответить
          </label>
          <textarea
            id="reply"
            rows={4}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="field"
          />
        </div>
        <button type="submit" disabled={submitting || !body.trim()} className="btn-primary">
          {submitting ? 'Отправка…' : 'Отправить'}
        </button>
      </form>
    </div>
  )
}
