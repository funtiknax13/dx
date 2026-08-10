import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { supportApi } from '../api/support'
import { ApiError } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { FormError } from '../components/AuthShell'
import { formatDate } from '../lib/format'
import { IconArrow, IconCheck, IconMail, IconSpark, IconUser, IconX } from '../components/ui/icons'

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

  const isOpen = ticket.status === 'open'

  return (
    <div className="container-page max-w-2xl py-10 sm:py-14">
      <div className="flex items-center justify-between gap-4">
        <span className="eyebrow text-signal">
          <IconMail width={16} height={16} /> Обращение #{ticket.id}
        </span>
        <Link
          to="/support"
          className="inline-flex items-center gap-1.5 font-mono text-xs text-ink-600 hover:text-signal"
        >
          <IconArrow width={13} height={13} className="rotate-180" /> Все обращения
        </Link>
      </div>

      {/* Status banner — impossible to miss which state the ticket is in. */}
      <div
        className={`mt-4 flex items-center gap-4 overflow-hidden rounded-xl2 p-5 shadow-card animate-fade-up sm:gap-5 sm:p-6 ${
          isOpen ? 'border border-signal/25 bg-signal-wash/60' : 'bg-ink text-paper'
        }`}
      >
        <span
          className={`relative grid h-12 w-12 shrink-0 place-items-center rounded-full sm:h-14 sm:w-14 ${
            isOpen ? 'bg-signal text-white' : 'bg-volt text-ink'
          }`}
        >
          {isOpen ? (
            <IconSpark width={24} height={24} />
          ) : (
            <IconCheck width={26} height={26} />
          )}
          {isOpen && (
            <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal/70" />
              <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-signal ring-2 ring-white" />
            </span>
          )}
        </span>

        <div className="min-w-0">
          <div className="font-display text-2xl leading-none sm:text-3xl">
            {isOpen ? 'Открыто' : 'Закрыто'}
          </div>
          <p className={`mt-1.5 text-sm ${isOpen ? 'text-ink-600' : 'text-paper/70'}`}>
            {isOpen ? 'Организаторы на связи — ответ придёт сюда' : 'Обращение решено и закрыто'}
          </p>
        </div>

        <div
          className={`ml-auto hidden shrink-0 text-right font-mono text-[0.68rem] uppercase tracking-[0.16em] sm:block ${
            isOpen ? 'text-clay' : 'text-paper/50'
          }`}
        >
          <div>Создано</div>
          <div className="mt-0.5 tabular">{formatDate(ticket.created_at)}</div>
        </div>
      </div>

      {/* Message timeline */}
      <div className="mt-8 space-y-3">
        {ticket.messages.map((m, i) => (
          <div
            key={m.id}
            className={`animate-fade-up rounded-xl2 border p-4 shadow-card ${
              m.is_staff ? 'border-signal/20 bg-signal-wash/40' : 'border-ink/[0.08] bg-white'
            }`}
            style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}
          >
            <div className="flex items-center gap-2.5">
              <span
                className={`grid h-6 w-6 shrink-0 place-items-center rounded-full ${
                  m.is_staff
                    ? 'bg-signal font-display text-[0.6rem] font-bold text-white'
                    : 'bg-ink text-paper'
                }`}
              >
                {m.is_staff ? 'DX' : <IconUser width={13} height={13} />}
              </span>
              <span className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-600">
                {m.is_staff ? 'Поддержка' : 'Вы'}
              </span>
              <span className="ml-auto font-mono text-[0.65rem] tabular text-clay">
                {formatDate(m.created_at)}
              </span>
            </div>
            <p className="mt-2.5 whitespace-pre-wrap text-sm leading-relaxed text-ink">{m.body}</p>
          </div>
        ))}
      </div>

      {isOpen ? (
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
      ) : (
        <div className="mt-6 rounded-xl2 border border-dashed border-ink/20 bg-paper-soft/50 p-6 text-center">
          <span className="mx-auto mb-2.5 grid h-10 w-10 place-items-center rounded-full bg-ink/[0.06] text-ink-600">
            <IconCheck width={20} height={20} />
          </span>
          <p className="text-sm text-ink-600">
            Обращение закрыто. Если вопрос не решён —{' '}
            <Link to="/support" className="font-semibold text-signal hover:underline">
              создайте новое обращение
            </Link>
            .
          </p>
        </div>
      )}
    </div>
  )
}
