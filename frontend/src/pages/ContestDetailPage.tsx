import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { contestsApi } from '../api/contests'
import { media } from '../api/client'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../lib/useAsync'
import { formatDate } from '../lib/format'
import { Avatar } from '../components/ui/Avatar'
import { Modal } from '../components/ui/Modal'
import { PageLoader, Spinner } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconCalendar, IconCheck, IconTrophy } from '../components/ui/icons'
import type {
  ContestDetail,
  ContestEntryValue,
  ContestField,
  ContestFieldType,
  MyContestEntry,
  PublicContestEntry,
} from '../types'

const PHASE_LABEL: Record<string, string> = {
  upcoming: 'Скоро начнётся',
  submissions_open: 'Приём заявок открыт',
  submissions_closed: 'Приём заявок завершён',
  voting_open: 'Идёт голосование',
  voting_closed: 'Итоги',
}

export function ContestDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data, loading, error, reload } = useAsync(() => contestsApi.detail(id!), [id])

  if (loading) return <PageLoader />
  if (error || !data) {
    return (
      <div className="container-page py-16">
        <StatePanel
          tone="error"
          title="Конкурс не найден"
          description={error ?? 'Проверьте ссылку или вернитесь к списку конкурсов.'}
          icon={<IconTrophy />}
          action={
            <div className="flex gap-3">
              <button onClick={reload} className="btn-ghost">
                Повторить
              </button>
              <Link to="/contests" className="btn-ink">
                К конкурсам
              </Link>
            </div>
          }
        />
      </div>
    )
  }

  const cover = media(data.cover_image)

  return (
    <article>
      <header className="relative overflow-hidden bg-ink text-paper">
        {cover ? (
          <>
            <img
              src={cover}
              alt=""
              className="absolute inset-0 h-full w-full object-cover opacity-45"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-ink via-ink/70 to-ink/30" />
          </>
        ) : (
          <div
            className="absolute inset-0 opacity-70"
            style={{
              backgroundImage:
                'radial-gradient(60% 80% at 85% 10%, rgba(255,255,255,0.14), transparent 60%)',
            }}
          />
        )}
        <div className="container-page relative py-14 sm:py-20">
          <Link
            to="/contests"
            className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em] text-paper/70 hover:text-volt"
          >
            Все конкурсы
          </Link>
          <div className="mt-5">
            <span className="chip bg-volt text-ink">{PHASE_LABEL[data.phase] ?? data.phase}</span>
          </div>
          <h1 className="mt-4 max-w-3xl font-display text-4xl leading-[1.03] sm:text-5xl">
            {data.title}
          </h1>
        </div>
      </header>

      <div className="container-page py-12 sm:py-16">
        {data.phase === 'upcoming' && <UpcomingTeaser contest={data} />}
        {data.phase === 'submissions_open' && <SubmissionSection contest={data} />}
        {data.phase === 'submissions_closed' && <ClosedNotice />}
        {(data.phase === 'voting_open' || data.phase === 'voting_closed') && (
          <VotingSection contest={data} />
        )}
      </div>
    </article>
  )
}

function UpcomingTeaser({ contest }: { contest: ContestDetail }) {
  return (
    <StatePanel
      title="Событие скоро начнётся"
      description={
        contest.submissions_open_at
          ? `Приём заявок откроется ${formatDate(contest.submissions_open_at, { day: 'numeric', month: 'long' })}.`
          : 'Условия конкурса появятся здесь, как только приём заявок откроется.'
      }
      icon={<IconTrophy />}
    />
  )
}

function ClosedNotice() {
  return (
    <StatePanel
      title="Приём конкурсных работ завершён"
      description="Ожидайте результаты — голосование скоро откроется."
      icon={<IconCalendar />}
    />
  )
}

// --- submission -----------------------------------------------------

function SubmissionSection({ contest }: { contest: ContestDetail }) {
  const { isAuthenticated } = useAuth()
  const {
    data: myEntry,
    loading,
    reload,
  } = useAsync(
    () => (isAuthenticated ? contestsApi.myEntry(contest.id) : Promise.resolve(null)),
    [contest.id, isAuthenticated],
  )
  const [formOpen, setFormOpen] = useState(false)

  return (
    <div className="mx-auto max-w-2xl">
      {contest.description && (
        <p className="mb-8 whitespace-pre-line text-base leading-relaxed text-ink-700">
          {contest.description}
        </p>
      )}

      {!isAuthenticated ? (
        <StatePanel
          title="Войдите, чтобы подать заявку"
          description="Участвовать в конкурсе могут только зарегистрированные участники."
          icon={<IconTrophy />}
          action={
            <Link to="/login" className="btn-ink">
              Войти
            </Link>
          }
        />
      ) : loading ? (
        <PageLoader />
      ) : myEntry?.status === 'approved' ? (
        <StatePanel
          title="Заявка принята"
          description="Ваша работа допущена к голосованию — изменить её уже нельзя."
          icon={<IconCheck />}
        />
      ) : (
        <>
          {myEntry?.status === 'pending' && (
            <p className="mb-5 chip bg-ink/10 text-ink-600">Заявка отправлена, ждёт проверки</p>
          )}
          {myEntry?.status === 'rejected' && (
            <div className="mb-5 rounded-xl2 border border-danger/20 bg-danger/5 p-4">
              <p className="font-semibold text-danger-600">Заявка отклонена</p>
              {myEntry.rejection_reason && (
                <p className="mt-1 text-sm text-ink-700">{myEntry.rejection_reason}</p>
              )}
              <p className="mt-1 text-sm text-clay">
                Доработайте и отправьте заявку заново, пока приём открыт.
              </p>
            </div>
          )}
          {contest.fields && (
            <button type="button" onClick={() => setFormOpen(true)} className="btn-ink">
              {myEntry ? 'Изменить заявку' : 'Отправить заявку'}
            </button>
          )}
          {formOpen && contest.fields && (
            <Modal title={myEntry ? 'Изменить заявку' : 'Отправить заявку'} onClose={() => setFormOpen(false)}>
              <EntryForm
                contest={contest}
                myEntry={myEntry ?? null}
                onSubmitted={() => {
                  setFormOpen(false)
                  reload()
                }}
              />
            </Modal>
          )}
        </>
      )}
    </div>
  )
}

function EntryForm({
  contest,
  myEntry,
  onSubmitted,
}: {
  contest: ContestDetail
  myEntry: MyContestEntry | null
  onSubmitted: () => void
}) {
  const existingValues = new Map((myEntry?.values ?? []).map((v) => [v.field_id, v.value ?? '']))
  const [texts, setTexts] = useState<Record<number, string>>(() => {
    const out: Record<number, string> = {}
    for (const f of contest.fields ?? []) {
      if (f.field_type !== 'image' && f.field_type !== 'gpx') {
        out[f.id] = existingValues.get(f.id) ?? ''
      }
    }
    return out
  })
  const [files, setFiles] = useState<Record<number, File>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<number, string>>({})

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setFieldErrors({})
    try {
      const values: Record<string, string | File> = {}
      for (const f of contest.fields ?? []) {
        if (f.field_type === 'image' || f.field_type === 'gpx') {
          if (files[f.id]) values[`field_${f.id}`] = files[f.id]
        } else {
          values[`field_${f.id}`] = texts[f.id] ?? ''
        }
      }
      await contestsApi.submit(contest.id, values)
      onSubmitted()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const data = err.data as { detail?: { errors?: Record<string, string> } }
        const errs = data?.detail?.errors
        if (errs) {
          const mapped: Record<number, string> = {}
          for (const [k, v] of Object.entries(errs)) mapped[Number(k)] = v
          setFieldErrors(mapped)
        }
        setError('Проверьте поля ниже')
      } else {
        setError(err instanceof Error ? err.message : 'Не удалось отправить заявку')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      {(contest.fields ?? []).map((f) => (
        <ContestFieldInput
          key={f.id}
          field={f}
          value={texts[f.id] ?? ''}
          onTextChange={(v) => setTexts((t) => ({ ...t, [f.id]: v }))}
          onFileChange={(file) => setFiles((fl) => ({ ...fl, [f.id]: file }))}
          existingFileUrl={
            f.field_type === 'image' || f.field_type === 'gpx'
              ? media(existingValues.get(f.id))
              : undefined
          }
          error={fieldErrors[f.id]}
        />
      ))}
      {error && <p className="text-sm text-danger-600">{error}</p>}
      <button type="submit" disabled={busy} className="btn-ink">
        {busy ? <Spinner /> : myEntry ? 'Отправить заново' : 'Отправить на проверку'}
      </button>
    </form>
  )
}

function ContestFieldInput({
  field,
  value,
  onTextChange,
  onFileChange,
  existingFileUrl,
  error,
}: {
  field: ContestField
  value: string
  onTextChange: (v: string) => void
  onFileChange: (f: File) => void
  existingFileUrl?: string
  error?: string
}) {
  const label = `${field.label}${field.required ? ' *' : ''}`
  return (
    <div>
      <label className="field-label">{label}</label>
      {field.description && <p className="mb-1.5 text-xs text-clay">{field.description}</p>}
      {field.field_type === 'long_text' ? (
        <textarea
          className="field"
          rows={4}
          value={value}
          onChange={(e) => onTextChange(e.target.value)}
        />
      ) : field.field_type === 'number' ? (
        <input
          type="number"
          step="any"
          className="field"
          value={value}
          onChange={(e) => onTextChange(e.target.value)}
        />
      ) : field.field_type === 'url' ? (
        <input
          type="url"
          className="field"
          placeholder="https://"
          value={value}
          onChange={(e) => onTextChange(e.target.value)}
        />
      ) : field.field_type === 'image' || field.field_type === 'gpx' ? (
        <div>
          {existingFileUrl && (
            <p className="mb-1.5 text-xs text-clay">
              Уже загружено:{' '}
              <a href={existingFileUrl} target="_blank" rel="noreferrer" className="text-signal">
                открыть
              </a>{' '}
              — выберите новый файл, только если хотите его заменить.
            </p>
          )}
          <input
            type="file"
            accept={field.field_type === 'image' ? 'image/png,image/jpeg,image/webp' : '.gpx'}
            className="field"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) onFileChange(f)
            }}
          />
        </div>
      ) : (
        <input
          type="text"
          className="field"
          value={value}
          onChange={(e) => onTextChange(e.target.value)}
        />
      )}
      {error && <p className="mt-1.5 text-xs text-danger-600">{error}</p>}
    </div>
  )
}

// --- voting -----------------------------------------------------

function VotingSection({ contest }: { contest: ContestDetail }) {
  const { isAuthenticated } = useAuth()
  const { data, loading, error, reload } = useAsync(() => contestsApi.entries(contest.id), [
    contest.id,
  ])
  const [voteError, setVoteError] = useState<string | null>(null)
  const [votingFor, setVotingFor] = useState<number | null>(null)

  const vote = async (entryId: number) => {
    setVoteError(null)
    setVotingFor(entryId)
    try {
      await contestsApi.vote(contest.id, entryId)
      await reload()
    } catch (err) {
      setVoteError(err instanceof Error ? err.message : 'Не удалось проголосовать')
    } finally {
      setVotingFor(null)
    }
  }

  if (loading) return <PageLoader />
  if (error) return <StatePanel tone="error" title="Не удалось загрузить заявки" description={error} />
  if (!data || data.entries.length === 0) {
    return <StatePanel title="Заявок, прошедших проверку, пока нет" icon={<IconTrophy />} />
  }

  const fieldsById = new Map((contest.fields ?? []).map((f) => [f.id, f]))

  return (
    <div>
      {contest.phase === 'voting_closed' && !contest.results_published ? (
        <p className="mb-6 chip bg-ink/10 text-ink-600">Голосование завершено, подводятся итоги</p>
      ) : contest.phase === 'voting_closed' ? (
        <p className="mb-6 chip bg-volt text-ink">Итоги подведены</p>
      ) : null}
      {voteError && <p className="mb-4 text-sm text-danger-600">{voteError}</p>}
      {!isAuthenticated && contest.phase === 'voting_open' && (
        <p className="mb-6 text-sm text-clay">
          <Link to="/login" className="text-signal">
            Войдите
          </Link>
          , чтобы проголосовать.
        </p>
      )}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {data.entries.map((entry) => (
          <EntryCard
            key={entry.id}
            entry={entry}
            fieldsById={fieldsById}
            canVote={isAuthenticated && contest.phase === 'voting_open'}
            isMyVote={data.my_vote_entry_id === entry.id}
            showPlacement={contest.results_published}
            onVote={() => vote(entry.id)}
            voting={votingFor === entry.id}
          />
        ))}
      </div>
    </div>
  )
}

function EntryCard({
  entry,
  fieldsById,
  canVote,
  isMyVote,
  showPlacement,
  onVote,
  voting,
}: {
  entry: PublicContestEntry
  fieldsById: Map<number, ContestField>
  canVote: boolean
  isMyVote: boolean
  showPlacement: boolean
  onVote: () => void
  voting: boolean
}) {
  return (
    <div className="flex flex-col rounded-xl2 border border-ink/[0.08] bg-white p-5 shadow-card">
      <div className="flex items-center gap-3">
        <Avatar
          first={entry.runner_name.split(' ')[0]}
          last={entry.runner_name.split(' ')[1]}
          src={entry.avatar}
          size="sm"
        />
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{entry.runner_name}</p>
        </div>
        {showPlacement && entry.placement && (
          <span className="ml-auto chip bg-volt text-ink">#{entry.placement}</span>
        )}
      </div>
      <div className="mt-4 space-y-2">
        {entry.values.map((v) => (
          <EntryValueDisplay key={v.field_id} value={v} field={fieldsById.get(v.field_id)} />
        ))}
      </div>
      <div className="mt-auto flex items-center justify-between pt-5">
        {entry.vote_count != null && (
          <span className="font-mono text-xs text-clay">{entry.vote_count} голосов</span>
        )}
        {canVote && (
          <button
            onClick={onVote}
            disabled={voting || isMyVote}
            className={`btn-sm ${isMyVote ? 'bg-volt text-ink' : 'btn-ink'}`}
          >
            {isMyVote ? 'Ваш голос' : voting ? <Spinner /> : 'Голосовать'}
          </button>
        )}
      </div>
    </div>
  )
}

function EntryValueDisplay({
  value,
  field,
}: {
  value: ContestEntryValue
  field: ContestField | undefined
}) {
  if (!value.value) return null
  const type: ContestFieldType = field?.field_type ?? 'text'
  const label = field?.label ?? ''
  if (type === 'url') {
    return (
      <p className="text-sm">
        <span className="text-clay">{label}: </span>
        <a
          href={value.value}
          target="_blank"
          rel="noreferrer"
          className="break-all text-signal hover:underline"
        >
          {value.value}
        </a>
      </p>
    )
  }
  if (type === 'image') {
    return <img src={media(value.value)} alt={label} className="rounded-xl" />
  }
  if (type === 'gpx') {
    return (
      <a href={media(value.value)} target="_blank" rel="noreferrer" className="text-sm text-signal">
        Скачать GPX
      </a>
    )
  }
  return (
    <p className="text-sm text-ink-700">
      <span className="text-clay">{label}: </span>
      {value.value}
    </p>
  )
}
