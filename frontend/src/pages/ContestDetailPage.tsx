import { Suspense, lazy, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { contestsApi } from '../api/contests'
import { media } from '../api/client'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../lib/useAsync'
import { formatDate, formatTime, plural } from '../lib/format'
import { parseJsonList } from '../lib/jsonList'
import { FIELD_LABELS } from '../lib/profileFieldLabels'
import { Avatar } from '../components/ui/Avatar'
import { ElevationProfile } from '../components/ElevationProfile'
import { ImageLightbox } from '../components/ui/ImageLightbox'
import { Modal } from '../components/ui/Modal'
import { PageLoader, Spinner } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { IconCalendar, IconTrophy } from '../components/ui/icons'
import type {
  ContestDetail,
  ContestEntryValue,
  ContestField,
  ContestFieldType,
  MyContestEntry,
  PublicContestEntry,
} from '../types'

// Lazy — MapLibre GL is heavy, so it only downloads when a gpx map is
// actually expanded (see GpxMapToggle below).
const RouteMap = lazy(() => import('../components/RouteMap').then((m) => ({ default: m.RouteMap })))

const PHASE_LABEL: Record<string, string> = {
  upcoming: 'Скоро начнётся',
  submissions_open: 'Приём заявок открыт',
  submissions_closed: 'Приём заявок завершён',
  voting_open: 'Идёт голосование',
  voting_closed: 'Итоги',
}

function windowText(openAt: string | null, closeAt: string | null): string | null {
  if (!openAt && !closeAt) return null
  const open = openAt ? `${formatDate(openAt, { day: 'numeric', month: 'long' })}, в ${formatTime(openAt)}` : null
  const close = closeAt ? `${formatDate(closeAt, { day: 'numeric', month: 'long' })}, в ${formatTime(closeAt)}` : null
  if (open && close) return `с ${open} по ${close}`
  if (close) return `до ${close}`
  return `с ${open}`
}

export function ContestDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const { data, loading, error, reload } = useAsync(() => contestsApi.detail(id!), [id, user])

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
  const submissionWindow = windowText(contest.submissions_open_at, contest.submissions_close_at)
  const votingWindow = windowText(contest.voting_open_at, contest.voting_close_at)
  return (
    <div className="mx-auto max-w-2xl">
      <h2 className="mb-4 font-display text-2xl text-ink">О конкурсе</h2>
      {contest.description && (
        <p className="mb-6 whitespace-pre-line break-words text-base leading-relaxed text-ink-700">
          {contest.description}
        </p>
      )}
      {(submissionWindow || votingWindow) && (
        <dl className="mb-6 space-y-4 rounded-xl2 border border-ink/[0.08] bg-white p-5 shadow-card">
          {submissionWindow && <div>
            <dt className="font-semibold text-ink">Приём работ</dt>
            <dd className="mt-1 text-sm text-clay">{submissionWindow}</dd>
          </div>}
          {votingWindow && <div>
            <dt className="font-semibold text-ink">Голосование</dt>
            <dd className="mt-1 text-sm text-clay">{votingWindow}</dd>
          </div>}
        </dl>
      )}
      <StatePanel
        title="Событие скоро начнётся"
        description={contest.submissions_open_at
          ? 'Подать работу можно будет после открытия приёма заявок.'
          : 'Организатор сообщит дату открытия приёма заявок.'}
        icon={<IconTrophy />}
      />
    </div>
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

type Editing = { entry: MyContestEntry | null } | null

function ContestAccessNotice({ contest }: { contest: ContestDetail }) {
  const reason = contest.lock_reason
  if (!reason) return null
  const anonymous = reason === 'anonymous'
  const pending = reason === 'profile_pending_review'
  return (
    <StatePanel
      title={anonymous ? 'Войдите, чтобы участвовать' : pending ? 'Анкета на проверке' : 'Заполните профиль на 100%'}
      description={pending
        ? 'Отправка работ и голосование станут доступны после проверки профиля.'
        : contest.missing_fields.length
            ? `Осталось: ${contest.missing_fields.map((f) => FIELD_LABELS[f] ?? f).join(', ')}.`
            : 'Для отправки работ и голосования заполните профиль и подтвердите почту. Участие в пробежках и анкета новичка не требуются.'}
      action={<Link to={anonymous ? '/login' : '/profile'} className="btn-ink">
        {anonymous ? 'Войти' : 'В профиль'}
      </Link>}
    />
  )
}

function SubmissionSection({ contest }: { contest: ContestDetail }) {
  const { isAuthenticated } = useAuth()
  const {
    data: myEntries,
    loading,
    reload,
  } = useAsync(
    () => (isAuthenticated ? contestsApi.myEntries(contest.id) : Promise.resolve([])),
    [contest.id, isAuthenticated],
  )
  const [editing, setEditing] = useState<Editing>(null)

  const entries = myEntries ?? []
  const atCap = contest.max_entries_per_runner != null && entries.length >= contest.max_entries_per_runner
  const submissionWindow = windowText(contest.submissions_open_at, contest.submissions_close_at)

  return (
    <div className="mx-auto max-w-2xl">
      {contest.description && (
        <p className="mb-4 whitespace-pre-line text-base leading-relaxed text-ink-700">
          {contest.description}
        </p>
      )}
      {submissionWindow && (
        <p className="mb-8 text-sm text-clay">Приём заявок {submissionWindow}.</p>
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
      ) : contest.lock_reason ? (
        <ContestAccessNotice contest={contest} />
      ) : loading ? (
        <PageLoader />
      ) : (
        <>
          {entries.length > 0 && (
            <div className="mb-5 space-y-3">
              {entries.map((entry) => (
                <MyEntryCard key={entry.id} entry={entry} onEdit={() => setEditing({ entry })} />
              ))}
            </div>
          )}
          {contest.fields && !atCap && (
            <button type="button" onClick={() => setEditing({ entry: null })} className="btn-ink">
              {entries.length === 0 ? 'Отправить заявку' : 'Отправить ещё одну заявку'}
            </button>
          )}
          {contest.fields && atCap && (
            <p className="text-sm text-clay">
              Достигнут лимит заявок на одного участника ({contest.max_entries_per_runner}).
            </p>
          )}
          {editing && contest.fields && (
            <Modal
              title={editing.entry ? 'Изменить заявку' : 'Отправить заявку'}
              onClose={() => setEditing(null)}
            >
              <EntryForm
                contest={contest}
                entry={editing.entry}
                onSubmitted={() => {
                  setEditing(null)
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

function MyEntryCard({ entry, onEdit }: { entry: MyContestEntry; onEdit: () => void }) {
  return (
    <div className="rounded-xl2 border border-ink/[0.08] bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        {entry.status === 'approved' ? (
          <span className="chip bg-volt text-ink">Принята</span>
        ) : entry.status === 'rejected' ? (
          <span className="chip bg-danger/10 text-danger-600">Отклонена</span>
        ) : (
          <span className="chip bg-ink/10 text-ink-600">Ждёт проверки</span>
        )}
        {entry.status !== 'approved' && (
          <button type="button" onClick={onEdit} className="btn-ghost btn-sm">
            Изменить
          </button>
        )}
      </div>
      {entry.status === 'rejected' && entry.rejection_reason && (
        <p className="mt-2 text-sm text-ink-700">{entry.rejection_reason}</p>
      )}
    </div>
  )
}

function EntryForm({
  contest,
  entry,
  onSubmitted,
}: {
  contest: ContestDetail
  entry: MyContestEntry | null
  onSubmitted: () => void
}) {
  const existingValues = new Map((entry?.values ?? []).map((v) => [v.field_id, v.value ?? '']))
  const [texts, setTexts] = useState<Record<number, string>>(() => {
    const out: Record<number, string> = {}
    for (const f of contest.fields ?? []) {
      if (f.field_type !== 'image' && f.field_type !== 'gpx') {
        out[f.id] = existingValues.get(f.id) ?? ''
      }
    }
    return out
  })
  const [files, setFiles] = useState<Record<number, File[]>>({})
  const [retainedImages, setRetainedImages] = useState<Record<number, string[]>>(() =>
    Object.fromEntries((contest.fields ?? []).filter((f) => f.field_type === 'image')
      .map((f) => [f.id, parseJsonList(existingValues.get(f.id))])),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<number, string>>({})

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setFieldErrors({})
    try {
      const values: Record<string, string | File | File[]> = {}
      for (const f of contest.fields ?? []) {
        if (f.field_type === 'image') {
          if (files[f.id]?.length) values[`field_${f.id}`] = files[f.id]
          values[`keep_field_${f.id}`] = JSON.stringify(retainedImages[f.id] ?? [])
        } else if (f.field_type === 'gpx') {
          if (files[f.id]?.[0]) values[`field_${f.id}`] = files[f.id][0]
        } else {
          values[`field_${f.id}`] = texts[f.id] ?? ''
        }
      }
      await contestsApi.submit(contest.id, values, entry?.id)
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
        setError('Заполните все обязательные поля')
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
        <div key={f.id}>
          {f.field_type === 'image' ? (
            <ContestImages
              field={f}
              files={files[f.id] ?? []}
              retained={retainedImages[f.id] ?? []}
              onFilesChange={(fl) => setFiles((cur) => ({ ...cur, [f.id]: fl }))}
              onRetainedChange={(paths) => setRetainedImages((cur) => ({ ...cur, [f.id]: paths }))}
              error={fieldErrors[f.id]}
            />
          ) : (
            <ContestFieldInput
              field={f}
              value={texts[f.id] ?? ''}
              onTextChange={(v) => setTexts((t) => ({ ...t, [f.id]: v }))}
              onFilesChange={(fl) => setFiles((cur) => ({ ...cur, [f.id]: fl }))}
              selectedFiles={files[f.id] ?? []}
              existingFileUrls={
                f.field_type === 'gpx'
                  ? parseJsonList(existingValues.get(f.id)).map((p) => media(p)!).filter(Boolean)
                  : undefined
              }
              error={fieldErrors[f.id]}
            />
          )}
          {f.field_type === 'gpx' && entry && existingValues.get(f.id) && (
            <GpxMapToggle contestId={contest.id} entryId={entry.id} fieldId={f.id} />
          )}
        </div>
      ))}
      {error && <p className="text-sm text-danger-600">{error}</p>}
      <button type="submit" disabled={busy} className="btn-ink">
        {busy ? <Spinner /> : entry ? 'Отправить заново' : 'Отправить на проверку'}
      </button>
    </form>
  )
}

function NewPhoto({ file }: { file: File }) {
  const [url, setUrl] = useState<string>()
  useEffect(() => {
    const next = URL.createObjectURL(file)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [file])
  return <img src={url} alt={file.name} className="h-24 w-full rounded-lg object-cover" />
}

function ContestImages({ field, files, retained, onFilesChange, onRetainedChange, error }: {
  field: ContestField
  files: File[]
  retained: string[]
  onFilesChange: (files: File[]) => void
  onRetainedChange: (paths: string[]) => void
  error?: string
}) {
  const count = files.length + retained.length
  return (
    <div>
      <label htmlFor={`photos-${field.id}`} className="field-label">{field.label}{field.required ? ' *' : ''}</label>
      {field.description && <p className="mb-1.5 text-xs text-clay">{field.description}</p>}
      <div className="mb-3 grid grid-cols-3 gap-2">
        {retained.map((path, i) => (
          <div key={path}>
            <img src={media(path)} alt={`Фото ${i + 1}`} className="h-24 w-full rounded-lg object-cover" />
            <button type="button" className="btn-ghost btn-sm mt-1 w-full" aria-label={`Удалить фото ${i + 1}`}
              onClick={() => onRetainedChange(retained.filter((p) => p !== path))}>Удалить</button>
          </div>
        ))}
        {files.map((file, i) => (
          <div key={`${file.name}-${i}`}>
            <NewPhoto file={file} />
            <button type="button" className="btn-ghost btn-sm mt-1 w-full" aria-label={`Удалить ${file.name}`}
              onClick={() => onFilesChange(files.filter((_, index) => index !== i))}>Удалить</button>
          </div>
        ))}
      </div>
      <ContestFilePicker
        id={`photos-${field.id}`}
        accept="image/png,image/jpeg,image/webp"
        multiple
        label={count ? 'Загрузить ещё файлы' : 'Загрузить файлы'}
        onSelect={(chosen) => onFilesChange([...files, ...chosen])}
      />
      <p role="status" className="mt-2 text-sm text-clay">
        {count ? `Файлов: ${count}` : 'Файлы не загружены'}
      </p>
      <p className="mt-1 text-xs text-clay">Новые фотографии добавляются к выбранным. Изменения сохранятся при отправке заявки.</p>
      {error && <p className="mt-1.5 text-xs text-danger-600">{error}</p>}
    </div>
  )
}

function ContestFilePicker({ id, accept, multiple = false, label, onSelect }: {
  id: string
  accept: string
  multiple?: boolean
  label: string
  onSelect: (files: File[]) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <>
      <input
        ref={input}
        id={id}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(e) => {
          const chosen = Array.from(e.target.files ?? [])
          if (chosen.length) onSelect(chosen)
          e.target.value = ''
        }}
      />
      <button type="button" className="btn-ghost" onClick={() => input.current?.click()}>
        {label}
      </button>
    </>
  )
}

function ContestFieldInput({
  field,
  value,
  onTextChange,
  onFilesChange,
  selectedFiles,
  existingFileUrls,
  error,
}: {
  field: ContestField
  value: string
  onTextChange: (v: string) => void
  onFilesChange: (files: File[]) => void
  selectedFiles: File[]
  existingFileUrls?: string[]
  error?: string
}) {
  const label = `${field.label}${field.required ? ' *' : ''}`
  const selected = field.field_type === 'multi_select' ? parseJsonList(value) : []

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
      ) : field.field_type === 'multi_select' ? (
        <div className="space-y-1.5">
          {(field.options ?? []).map((opt) => (
            <label key={opt} className="flex items-center gap-2 text-sm text-ink-700">
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={(e) => {
                  const next = e.target.checked
                    ? [...selected, opt]
                    : selected.filter((o) => o !== opt)
                  onTextChange(JSON.stringify(next))
                }}
              />
              {opt}
            </label>
          ))}
        </div>
      ) : field.field_type === 'gpx' ? (
        <div>
          {existingFileUrls && existingFileUrls.length > 0 && (
            <div className="mb-2">
              <a href={existingFileUrls[0]} target="_blank" rel="noreferrer" className="text-sm text-signal">
                Открыть текущий GPX
              </a>
              <p className="mt-1 text-xs text-clay">
                Уже загружено — выберите новый файл, только если хотите заменить.
              </p>
            </div>
          )}
          <ContestFilePicker
            id={`gpx-${field.id}`}
            accept=".gpx"
            label={selectedFiles.length || existingFileUrls?.length ? 'Заменить GPX' : 'Загрузить GPX'}
            onSelect={onFilesChange}
          />
          <p role="status" className="mt-2 break-words text-sm text-clay">
            {selectedFiles[0] ? `Выбран файл: ${selectedFiles[0].name}`
              : existingFileUrls?.length ? 'Файл уже загружен' : 'Файлы не загружены'}
          </p>
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

/** Click to lazily fetch and reveal the gpx field's route as a map — used
 * in EntryForm's own existing-file preview, where someone is filling out a
 * form and doesn't necessarily want a map popping in. Voting shows the map
 * immediately instead (see GpxMap below) — more informative at a glance. */
function GpxMapToggle({
  contestId,
  entryId,
  fieldId,
}: {
  contestId: number
  entryId: number
  fieldId: number
}) {
  const [open, setOpen] = useState(false)
  const { data, loading, error } = useAsync(
    () => (open ? contestsApi.routeMap(contestId, entryId, fieldId) : Promise.resolve(null)),
    [open, contestId, entryId, fieldId],
  )

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mt-1.5 text-xs text-signal">
        Показать маршрут на карте
      </button>
    )
  }
  if (loading) return <div className="mt-2 h-[200px] animate-pulse rounded-xl2 bg-ink/5" />
  if (error || !data) return <p className="mt-2 text-xs text-danger-600">Не удалось загрузить маршрут</p>

  return (
    <div className="mt-2 space-y-2">
      <Suspense fallback={<div className="h-[200px] animate-pulse rounded-xl2 bg-ink/5" />}>
        <RouteMap points={data.points} className="h-[200px]" />
      </Suspense>
      {data.elevation.length > 1 && (
        <ElevationProfile data={data.elevation} ascent={data.ascent_m} descent={data.descent_m} />
      )}
    </div>
  )
}

/** Always-visible variant for voting/results — the map renders right away
 * instead of behind a "показать" click, more informative for comparing
 * entries at a glance. The download link stays alongside it. */
function GpxMap({
  contestId,
  entryId,
  fieldId,
}: {
  contestId: number
  entryId: number
  fieldId: number
}) {
  const { data, loading, error } = useAsync(
    () => contestsApi.routeMap(contestId, entryId, fieldId),
    [contestId, entryId, fieldId],
  )

  if (loading) return <div className="mt-2 h-[220px] animate-pulse rounded-xl2 bg-ink/5" />
  if (error || !data) return <p className="mt-2 text-xs text-danger-600">Не удалось загрузить маршрут</p>

  return (
    <div className="mt-2 space-y-2">
      <Suspense fallback={<div className="h-[220px] animate-pulse rounded-xl2 bg-ink/5" />}>
        <RouteMap points={data.points} className="h-[220px]" />
      </Suspense>
      {data.elevation.length > 1 && (
        <ElevationProfile data={data.elevation} ascent={data.ascent_m} descent={data.descent_m} />
      )}
    </div>
  )
}

// --- voting -----------------------------------------------------

function VotingSection({ contest }: { contest: ContestDetail }) {
  const { isAuthenticated, user } = useAuth()
  const { data, loading, error, setData } = useAsync(() => contestsApi.entries(contest.id), [
    contest.id, user?.id,
  ])
  const [notice, setNotice] = useState<string | null>(null)
  const [voteChoice, setVoteChoice] = useState<PublicContestEntry | null>(null)
  const [votingFor, setVotingFor] = useState<number | null>(null)
  const voteInFlight = useRef(false)

  const vote = async (entryId: number) => {
    if (voteInFlight.current || !data || data.my_vote_entry_id != null) return
    voteInFlight.current = true
    setVotingFor(entryId)
    try {
      await contestsApi.vote(contest.id, entryId)
      setData({ ...data, my_vote_entry_id: entryId,
        entries: data.entries.map((entry) => entry.id === entryId && entry.vote_count != null
          ? { ...entry, vote_count: entry.vote_count + 1 } : entry),
      })
      setNotice('Ваш голос учтен')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Не удалось проголосовать')
      // Another tab may have cast the final vote already.
      try { setData(await contestsApi.entries(contest.id)) } catch { /* keep current works visible */ }
    } finally {
      setVoteChoice(null)
      setVotingFor(null)
      voteInFlight.current = false
    }
  }

  if (loading) return <PageLoader />
  if (error) return <StatePanel tone="error" title="Не удалось загрузить заявки" description={error} />
  if (!data) {
    return <StatePanel title="Заявок, прошедших проверку, пока нет" icon={<IconTrophy />} />
  }

  const fieldsById = new Map((contest.fields ?? []).map((f) => [f.id, f]))

  // Submission order stays fixed until the published results.
  const sorted = [...data.entries].sort((a, b) => {
    if (contest.results_published) return (a.placement ?? Infinity) - (b.placement ?? Infinity)
    return a.id - b.id
  })
  const podiumEntries = contest.results_published
    ? sorted.filter((entry) => entry.placement != null && entry.placement >= 1 && entry.placement <= 3)
    : []
  const podiumIds = new Set(podiumEntries.map((e) => e.id))
  const restEntries = sorted.filter((e) => !podiumIds.has(e.id))
  const chosenTitle = voteChoice?.values.find((value) => {
    const type = fieldsById.get(value.field_id)?.field_type
    return (type === 'text' || type === 'long_text') && value.value?.trim()
  })?.value

  return (
    <div>
      {contest.phase === 'voting_closed' && !contest.results_published ? (
        <p className="mb-6 font-display text-xl text-ink">Голосование завершено — подводятся итоги</p>
      ) : contest.phase === 'voting_closed' ? (
        <p className="mb-6 inline-block rounded-xl2 bg-volt px-4 py-2 font-display text-xl text-ink">
          Итоги подведены
        </p>
      ) : null}
      {notice && <Modal title={notice} onClose={() => setNotice(null)}>
        <button type="button" className="btn-ink" onClick={() => setNotice(null)}>Понятно</button>
      </Modal>}
      {voteChoice && <Modal
        title="Подтвердите голос"
        onClose={() => setVoteChoice(null)}
        closeDisabled={votingFor != null}
      >
        <p className="break-words text-sm leading-relaxed text-ink-700">
          Вы голосуете за работу{' '}
          <span className="font-semibold text-ink">«{chosenTitle || `Работа №${voteChoice.id}`}»</span>
          {' '}участника <span className="font-semibold text-ink">{voteChoice.runner_name}</span>.
        </p>
        <p className="mt-3 text-sm text-clay">Изменить голос после подтверждения нельзя.</p>
        <div className="mt-5 flex flex-wrap gap-3">
          <button type="button" className="btn-ghost" disabled={votingFor != null}
            onClick={() => setVoteChoice(null)} autoFocus>Отмена</button>
          <button type="button" className="btn-ink" disabled={votingFor != null}
            onClick={() => vote(voteChoice.id)}>
            {votingFor != null ? <Spinner /> : 'Подтвердить голос'}
          </button>
        </div>
      </Modal>}
      {data.statistics && (
        <dl className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {([
            ['Участников', data.statistics.participants],
            ['Конкурсных работ', data.statistics.entries],
            ['Проголосовавших', data.statistics.voters],
          ] as const).map(([label, count]) => (
            <div key={label} className="rounded-xl2 border border-ink/[0.08] bg-white p-5 shadow-card">
              <dt className="text-sm text-clay">{label}</dt>
              <dd className="mt-2 font-display text-3xl tabular text-ink">{count}</dd>
            </div>
          ))}
        </dl>
      )}
      {contest.phase === 'voting_open' && data.my_vote_entry_id != null && (
        <p className="mb-6 rounded-xl2 bg-paper-deep p-4 text-sm text-ink">Ваш голос учтен. Изменить голос нельзя. Вы можете продолжить просмотр работ.</p>
      )}
      {isAuthenticated && contest.lock_reason && contest.phase === 'voting_open' && data.my_vote_entry_id == null && (
        <div className="mb-6"><ContestAccessNotice contest={contest} /></div>
      )}
      {!isAuthenticated && contest.phase === 'voting_open' && (
        <p className="mb-6 text-sm text-clay">
          <Link to="/login" className="text-signal">
            Войдите
          </Link>
          , чтобы проголосовать.
        </p>
      )}
      {podiumEntries.length > 0 && (
        <>
          <h2 className="mb-6 font-display text-2xl text-ink">Победители:</h2>
          <ContestPodium entries={podiumEntries} fieldsById={fieldsById} contestId={contest.id} />
        </>
      )}
      {contest.results_published && <h2 className="mb-6 font-display text-2xl text-ink">Все конкурсные работы:</h2>}
      {restEntries.length === 0 && <p className="text-sm text-clay">{podiumEntries.length ? 'Других конкурсных работ нет.' : 'Заявок, прошедших проверку, пока нет.'}</p>}
      {restEntries.length > 0 && (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {restEntries.map((entry) => (
            <EntryCard
              key={entry.id}
              contestId={contest.id}
              entry={entry}
              fieldsById={fieldsById}
              canVote={isAuthenticated && !contest.lock_reason && contest.phase === 'voting_open' && data.my_vote_entry_id == null}
              isMyVote={data.my_vote_entry_id === entry.id}
              showPlacement={contest.results_published}
              onVote={() => {
                if (voteInFlight.current || data.my_vote_entry_id != null) return
                if (entry.runner_id === user?.id) {
                  setNotice('Нельзя голосовать за свою заявку')
                } else {
                  setVoteChoice(entry)
                }
              }}
              voting={votingFor != null}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** Top-3 by admin-assigned placement, styled like the community rating's
 * own podium (1st/2nd/3rd, ranked by value shade not hue) — once results
 * are published a small corner number isn't prominent enough. */
function ContestPodium({
  entries,
  fieldsById,
  contestId,
}: {
  entries: PublicContestEntry[]
  fieldsById: Map<number, ContestField>
  contestId: number
}) {
  const order = ['sm:order-2', 'sm:order-1', 'sm:order-3']
  const heights = ['', 'sm:mt-8', 'sm:mt-14']
  const rings = ['ring-ink', 'ring-[#B4B4AF]', 'ring-[#D6D6D2]']
  const badges = ['bg-ink', 'bg-[#B4B4AF]', 'bg-[#D6D6D2]']
  const badgeText = ['text-paper', 'text-ink', 'text-ink']

  return (
    <div className="mb-8 grid gap-4 sm:grid-cols-3">
      {entries.map((entry) => {
        const i = (entry.placement ?? 1) - 1
        return (
          <div
            key={entry.id}
            className={`relative flex flex-col rounded-xl2 border border-ink/[0.08] bg-white p-5 text-center shadow-card ${order[i]} ${heights[i]}`}
          >
            <span
              className={`absolute -top-3 left-1/2 grid h-8 -translate-x-1/2 place-items-center whitespace-nowrap rounded-full px-3 font-display text-sm ${badges[i]} ${badgeText[i]}`}
            >
              {entry.placement} место
            </span>
            <Avatar
              first={entry.runner_name.split(' ')[0]}
              last={entry.runner_name.split(' ')[1]}
              src={entry.avatar}
              size="lg"
              className={`mx-auto ring-2 ${rings[i]}`}
              zoomable
            />
            <h3 className="mt-3 truncate font-display text-lg text-ink">{entry.runner_name}</h3>
            {entry.vote_count != null && (
              <div className="mt-2 flex items-baseline justify-center gap-1.5">
                <span className="font-display text-2xl tabular text-signal">{entry.vote_count}</span>
                <span className="font-mono text-xs text-clay">
                  {plural(entry.vote_count, 'голос', 'голоса', 'голосов')}
                </span>
              </div>
            )}
            <div className="mt-4 space-y-2 text-left">
              {entry.values.map((v) => (
                <EntryValueDisplay
                  key={v.field_id}
                  value={v}
                  field={fieldsById.get(v.field_id)}
                  contestId={contestId}
                  entryId={entry.id}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function EntryCard({
  contestId,
  entry,
  fieldsById,
  canVote,
  isMyVote,
  showPlacement,
  onVote,
  voting,
}: {
  contestId: number
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
          <span className="ml-auto chip bg-volt text-ink">{entry.placement} место</span>
        )}
      </div>
      <div className="mt-4 space-y-2">
        {entry.values.map((v) => (
          <EntryValueDisplay
            key={v.field_id}
            value={v}
            field={fieldsById.get(v.field_id)}
            contestId={contestId}
            entryId={entry.id}
          />
        ))}
      </div>
      <div className="mt-auto flex items-center justify-between pt-5">
        {entry.vote_count != null && (
          <span className="inline-flex items-baseline gap-1">
            <span className="font-display text-lg tabular text-signal">{entry.vote_count}</span>
            <span className="font-mono text-xs text-clay">
              {plural(entry.vote_count, 'голос', 'голоса', 'голосов')}
            </span>
          </span>
        )}
        {isMyVote ? <span className="chip bg-volt text-ink">Ваш голос</span> : canVote && (
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
  contestId,
  entryId,
}: {
  value: ContestEntryValue
  field: ContestField | undefined
  contestId: number
  entryId: number
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
    return <ImageGallery paths={parseJsonList(value.value)} label={label} />
  }
  if (type === 'gpx') {
    return (
      <div>
        <a
          href={media(value.value) ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-signal"
        >
          Скачать GPX
        </a>
        {field && <GpxMap contestId={contestId} entryId={entryId} fieldId={field.id} />}
      </div>
    )
  }
  if (type === 'multi_select') {
    const selected = parseJsonList(value.value)
    if (selected.length === 0) return null
    return (
      <div className="flex flex-wrap gap-1.5">
        {selected.map((opt) => (
          <span key={opt} className="chip bg-ink/10 text-ink-600">
            {opt}
          </span>
        ))}
      </div>
    )
  }
  return (
    <p className="text-sm text-ink-700">
      <span className="text-clay">{label}: </span>
      {value.value}
    </p>
  )
}

function ImageGallery({ paths, label }: { paths: string[]; label: string }) {
  const [open, setOpen] = useState<string | null>(null)
  const urls = paths.map((p) => media(p)).filter((u): u is string => Boolean(u))
  if (urls.length === 0) return null
  return (
    <>
      <div className="flex flex-wrap gap-2">
        {urls.map((url) => (
          <img
            key={url}
            src={url}
            alt={label}
            onClick={() => setOpen(url)}
            className="h-24 w-24 cursor-zoom-in rounded-xl object-cover"
          />
        ))}
      </div>
      {open && <ImageLightbox src={open} alt={label} onClose={() => setOpen(null)} />}
    </>
  )
}
