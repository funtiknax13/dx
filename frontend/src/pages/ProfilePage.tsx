import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { usersApi } from '../api/users'
import { guestsApi } from '../api/guests'
import { signupsApi, type AwaitingResultEntry } from '../api/signups'
import { attendanceApi } from '../api/attendance'
import { ApiError } from '../api/client'
import { ManualResultForm } from '../components/ManualResultForm'
import { useAsync } from '../lib/useAsync'
import {
  ageFromISO,
  formatDate,
  formatTime,
  fullName,
  nextRuPhoneValue,
  ruPhoneDigits,
} from '../lib/format'
import { Avatar } from '../components/ui/Avatar'
import { AvatarCropModal } from '../components/AvatarCropModal'
import { Field, PasswordField, SelectField } from '../components/ui/Field'
import { CityAutocomplete } from '../components/ui/CityAutocomplete'
import { RunningClubField } from '../components/ui/RunningClubField'
import {
  NAME_MAX_LENGTH,
  PASSWORD_HINT,
  capitalizeFirst,
  nameError,
  optionalNameError,
  passwordError,
} from '../lib/validation'
import { Spinner } from '../components/ui/Spinner'
import { FormError, FormSuccess } from '../components/AuthShell'
import { IconArrow, IconCalendar, IconUser } from '../components/ui/icons'
import { FIELD_LABELS } from '../lib/profileFieldLabels'
import type {
  Gender,
  GuestClaim,
  GuestProfile,
  MySignupEntry,
  PriorExperience,
  UpdateProfilePayload,
  User,
} from '../types'

type Tab = 'profile' | 'security'

export function ProfilePage() {
  const { user, setUser, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('profile')

  const stats = useAsync(() => usersApi.publicProfile(user!.id), [user?.id])
  const upcoming = useAsync(() => signupsApi.mine(), [user?.id])
  const awaiting = useAsync(() => signupsApi.awaitingResults(), [user?.id])
  const claims = useAsync(() => guestsApi.myClaims(), [user?.id])
  // Once a guest profile has already been claimed and approved, there's
  // nothing left to look for — keep offering the search only to accounts
  // that haven't matched one yet.
  const hasApprovedClaim = claims.data?.some((c) => c.status === 'approved') ?? false

  if (!user) return null

  return (
    <div className="container-page py-10 sm:py-14">
      {/* Profile header */}
      <div className="flex flex-col gap-6 rounded-xl2 border border-ink/[0.08] bg-white p-6 shadow-card sm:flex-row sm:items-center sm:justify-between sm:p-8">
        <div className="flex min-w-0 items-center gap-5">
          <AvatarUploader />
          <div className="min-w-0">
            <h1 className="break-words font-display text-2xl sm:text-3xl">
              {user.needs_reentry ? 'Имя ждёт подтверждения' : fullName(user.first_name, user.last_name)}
            </h1>
            <p className="mt-1 font-mono text-sm text-clay">{user.email}</p>
            <span className="mt-2 inline-flex chip bg-ink text-paper">{roleLabel(user.role)}</span>
          </div>
        </div>
        <Link
          to={`/users/${user.id}`}
          className="flex items-center gap-6 rounded-xl2 border border-transparent px-2 py-1 transition hover:border-ink/10"
        >
          <div className="text-center">
            <div className="font-display text-3xl tabular text-signal">
              {stats.data?.rating ?? user.rating ?? 0}
            </div>
            <div className="font-mono text-[0.62rem] uppercase tracking-[0.14em] text-clay">
              рейтинг
            </div>
          </div>
          <div className="text-center">
            <div className="font-display text-3xl tabular text-ink">
              {stats.data?.finished_count ?? 0}
            </div>
            <div className="font-mono text-[0.62rem] uppercase tracking-[0.14em] text-clay">
              финишей
            </div>
          </div>
          <span className="hidden text-sm font-semibold text-ink-600 hover:text-signal sm:inline-flex sm:items-center sm:gap-1">
            Статистика и достижения <IconArrow width={14} height={14} />
          </span>
        </Link>
      </div>

      {upcoming.data && upcoming.data.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-4 font-display text-xl">Предстоящие события</h3>
          <UpcomingSignups entries={upcoming.data} />
        </div>
      )}

      {awaiting.data && awaiting.data.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-1 font-display text-xl">Загрузить результат</h3>
          <p className="mb-4 text-sm text-ink-600">
            Прошедшие события, куда вы записаны. Можно загрузить свой результат, не дожидаясь
            протокола.
          </p>
          <AwaitingResults
            entries={awaiting.data}
            gender={user?.gender ?? null}
            onSubmitted={() => {
              awaiting.reload()
              stats.reload()
            }}
          />
        </div>
      )}

      {/* Tabs */}
      <div className="mt-8 flex gap-2 overflow-x-auto pb-1">
        {(
          [
            ['profile', 'Мои данные'],
            ['security', 'Безопасность'],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold transition ${
              tab === key ? 'bg-ink text-paper' : 'border border-ink/10 text-ink-600 hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'profile' && <ProfileForm onSaved={setUser} hasApprovedClaim={hasApprovedClaim} />}
        {tab === 'security' && (
          <div className="grid gap-6 lg:grid-cols-2">
            <PasswordForm />
            <div className="card p-6">
              <h3 className="font-display text-lg">Сессия</h3>
              <p className="mt-2 text-sm text-ink-600">
                Выход завершит текущую сессию на этом устройстве.
              </p>
              <button onClick={logout} className="btn-ghost mt-4">
                Выйти из аккаунта
              </button>
            </div>
            <DataExportCard />
            <DeleteAccountCard />
          </div>
        )}
      </div>
    </div>
  )
}

function UpcomingSignups({ entries }: { entries: MySignupEntry[] }) {
  return (
    <ul className="space-y-2">
      {entries.map((e) => (
        <li key={e.signup_id}>
          <Link
            to={`/groups/${e.group_id}`}
            className="flex items-center justify-between gap-4 rounded-xl2 border border-ink/[0.08] bg-white p-4 shadow-card transition hover:border-signal/40"
          >
            <div className="min-w-0">
              <p className="truncate font-display text-base text-ink">{e.event_title}</p>
              <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-600">
                <span className="inline-flex items-center gap-1">
                  <IconCalendar width={13} height={13} className="text-signal" />
                  {formatDate(e.event_date, { day: 'numeric', month: 'long' })}
                </span>
                {e.start_time && <span>старт {formatTime(e.start_time)}</span>}
                <span>{e.group_name}</span>
              </p>
            </div>
            <IconArrow width={16} height={16} className="shrink-0 text-clay" />
          </Link>
        </li>
      ))}
    </ul>
  )
}

function AwaitingResults({
  entries,
  gender,
  onSubmitted,
}: {
  entries: AwaitingResultEntry[]
  gender: Gender | null
  onSubmitted: () => void
}) {
  return (
    <ul className="space-y-3">
      {entries.map((e) => (
        <AwaitingResultRow key={e.signup_id} entry={e} gender={gender} onSubmitted={onSubmitted} />
      ))}
    </ul>
  )
}

function AwaitingResultRow({
  entry: e,
  gender,
  onSubmitted,
}: {
  entry: AwaitingResultEntry
  gender: Gender | null
  onSubmitted: () => void
}) {
  const [open, setOpen] = useState(false)
  const [dismissing, setDismissing] = useState(false)
  const pending = e.moderation_status === 'pending'
  const rejected = e.moderation_status === 'rejected'
  const didNotRunLabel = gender === 'female' ? 'Я не бегала' : gender === 'male' ? 'Я не бегал' : 'Я не бегал(а)'

  const dismiss = async () => {
    setDismissing(true)
    try {
      await signupsApi.remove(e.signup_id)
      onSubmitted()
    } finally {
      setDismissing(false)
    }
  }

  return (
    <li className="rounded-xl2 border border-ink/[0.08] bg-white shadow-card">
      <div className="flex items-center gap-4 p-4">
        <div className="min-w-0 flex-1">
          <Link
            to={`/groups/${e.group_id}`}
            className="block truncate font-display text-base text-ink hover:text-signal"
          >
            {e.event_title}
          </Link>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-600">
            <span className="inline-flex items-center gap-1">
              <IconCalendar width={13} height={13} className="text-signal" />
              {formatDate(e.event_date, { day: 'numeric', month: 'long' })}
            </span>
            <span>{e.group_name}</span>
          </p>
        </div>
        {pending ? (
          <span className="chip shrink-0 bg-ink/10 text-ink-600">На проверке</span>
        ) : (
          <div className="flex shrink-0 items-center gap-2">
            {rejected && <span className="chip bg-signal/10 text-signal-600">Отклонён</span>}
            <button
              onClick={dismiss}
              disabled={dismissing}
              className="btn-ghost btn-sm"
              type="button"
            >
              {didNotRunLabel}
            </button>
            <button onClick={() => setOpen((v) => !v)} className="btn-primary btn-sm" type="button">
              {open ? 'Закрыть' : rejected ? 'Загрузить заново' : 'Загрузить'}
            </button>
          </div>
        )}
      </div>
      {open && !pending && (
        <div className="border-t border-ink/[0.06] bg-paper-soft/40 p-4">
          <ManualResultForm
            onSubmit={(d) => attendanceApi.submitGroupResult(e.group_id, d)}
            onDone={() => {
              setOpen(false)
              onSubmitted()
            }}
          />
        </div>
      )}
    </li>
  )
}

function roleLabel(role: string) {
  return role === 'admin' ? 'Администратор' : role === 'organizer' ? 'Организатор' : 'Бегун'
}

// Values in a pending profile edit come straight from the backend's JSON diff
// (see ProfileEditRequest) — dates as plain ISO strings, gender as its raw
// enum value — reformat the ones that would otherwise look raw/unfriendly.
function formatPendingValue(field: string, value: string | number | null): string {
  if (value === null || value === '') return '—'
  if (field === 'birthday' && typeof value === 'string') return formatDate(value)
  if (field === 'gender') return value === 'male' ? 'Мужской' : value === 'female' ? 'Женский' : String(value)
  return String(value)
}

/** A field's still-pending proposed value, if any, else its current
 * (approved) one. The form must edit *this*, not the raw committed value —
 * otherwise resubmitting the form after touching only some fields silently
 * resends the stale committed value for every field it didn't prefill from
 * the pending edit, which the backend then reads as "revert this field",
 * wiping out whatever was still awaiting review on it (see
 * profile_review_service.submit_for_review, which diffs the whole payload
 * against the committed row every time). */
function pendingOrCurrent<T>(user: User | null | undefined, field: string, current: T): T {
  const changes = user?.pending_review?.changes
  if (changes && field in changes) return changes[field] as T
  return current
}

function AvatarUploader() {
  const { user, setUser } = useAuth()
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  // The picked file waits here while the user frames the crop in the modal.
  const [pending, setPending] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  const upload = async (file: File) => {
    setBusy(true)
    setError(null)
    try {
      const updated = await usersApi.uploadAvatar(file)
      setUser(updated)
      setPending(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось загрузить фото')
    } finally {
      setBusy(false)
    }
  }

  const missing = !user?.avatar_url

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="group relative inline-flex rounded-full"
        aria-label="Сменить аватар"
      >
        <Avatar
          first={user?.first_name}
          last={user?.last_name}
          src={user?.avatar_url}
          size="xl"
          className={missing ? 'ring-2 ring-danger ring-offset-2' : ''}
        />
        <span className="absolute inset-0 grid place-items-center rounded-full bg-ink/50 text-xs font-semibold text-paper opacity-0 transition-opacity group-hover:opacity-100">
          {busy ? <Spinner className="h-5 w-5" /> : 'Сменить'}
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) {
            setError(null)
            setPending(f)
          }
          e.target.value = ''
        }}
      />
      {missing && (
        <p className="mt-1.5 max-w-[6rem] text-center text-[0.65rem] text-danger-600">
          Нужно для рейтинга
        </p>
      )}
      {!missing && user?.avatar_review === 'pending' && (
        <p className="mt-1.5 max-w-[7rem] text-center text-[0.65rem] text-clay">
          Фото на проверке — пока видно только вам
        </p>
      )}
      {pending && (
        <AvatarCropModal
          file={pending}
          busy={busy}
          error={error}
          onCancel={() => {
            if (!busy) {
              setPending(null)
              setError(null)
            }
          }}
          onConfirm={(cropped) => void upload(cropped)}
        />
      )}
    </div>
  )
}

function ProfileForm({
  onSaved,
  hasApprovedClaim,
}: {
  onSaved: (u: User) => void
  hasApprovedClaim: boolean
}) {
  const { user } = useAuth()
  // Prefilled from any still-pending proposal rather than the raw committed
  // value — see pendingOrCurrent for why that matters.
  const [form, setForm] = useState({
    first_name: pendingOrCurrent(user, 'first_name', user?.first_name ?? ''),
    last_name: pendingOrCurrent(user, 'last_name', user?.last_name ?? ''),
    city: pendingOrCurrent(user, 'city', user?.city ?? ''),
    city_id: pendingOrCurrent(user, 'city_id', user?.city_id ?? null),
    gender: pendingOrCurrent(user, 'gender', (user?.gender ?? '') as Gender | ''),
    birthday: pendingOrCurrent(user, 'birthday', user?.birthday ?? ''),
    phone: pendingOrCurrent(user, 'phone', user?.phone ?? ''),
    prior_experience: (user?.prior_experience ?? '') as PriorExperience | '',
    parent_first_name: pendingOrCurrent(user, 'parent_first_name', user?.parent_first_name ?? ''),
    parent_last_name: pendingOrCurrent(user, 'parent_last_name', user?.parent_last_name ?? ''),
    parent_phone: pendingOrCurrent(user, 'parent_phone', user?.parent_phone ?? ''),
  })
  // Running club gets its own tri-state: text vs "not in a club" checkbox vs
  // untouched — see profile_completeness_service on the backend for why "" and
  // null mean different things here.
  const pendingClub = pendingOrCurrent(user, 'running_club', user?.running_club ?? null)
  const [noClub, setNoClub] = useState(pendingClub === '')
  const [club, setClub] = useState(pendingClub || '')
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(false)

  const set =
    (k: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setForm((f) => ({ ...f, [k]: e.target.value }))
      setSaved(false)
    }

  // Name fields (own + guardian) capitalise the first letter as you type.
  const setName =
    (k: 'first_name' | 'last_name' | 'parent_first_name' | 'parent_last_name') =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((f) => ({ ...f, [k]: capitalizeFirst(e.target.value) }))
      setSaved(false)
    }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const errs: Record<string, string> = {}
    const firstErr = nameError(form.first_name, 'Укажите имя')
    if (firstErr) errs.first_name = firstErr
    const lastErr = nameError(form.last_name, 'Укажите фамилию')
    if (lastErr) errs.last_name = lastErr
    // Guardian names are optional, but if filled they must pass the same rule.
    const parentFirstErr = optionalNameError(form.parent_first_name)
    if (parentFirstErr) errs.parent_first_name = parentFirstErr
    const parentLastErr = optionalNameError(form.parent_last_name)
    if (parentLastErr) errs.parent_last_name = parentLastErr
    // Already shown live next to the field (see futureBirthdayError below) —
    // re-checked here too so a future date can't slip through to the server.
    if (futureBirthdayError) errs.birthday = futureBirthdayError
    setFieldErrors(errs)
    if (Object.keys(errs).length > 0) return
    // Phone is optional, but if given it must be a full RU number.
    const phoneDigits = ruPhoneDigits(form.phone)
    if (form.phone.trim() && phoneDigits.length !== 10) {
      setError('Введите телефон полностью: +7 и 10 цифр')
      return
    }
    if (form.parent_phone.trim() && ruPhoneDigits(form.parent_phone).length !== 10) {
      setError('Телефон родителя укажите полностью: +7 и 10 цифр')
      return
    }
    setLoading(true)
    // City: a canonical pick sends both city_id and its name (the name is
    // also what the moderation queue displays — see profile_review.html;
    // city_id alone used to leave "Город" missing from that view since
    // nothing there was ever staged as a "city" change); a legacy free-text
    // value with no id is kept as text; empty clears both.
    const cityFields: Pick<UpdateProfilePayload, 'city' | 'city_id'> =
      form.city_id != null
        ? { city_id: form.city_id, city: form.city.trim() || null }
        : form.city.trim()
          ? { city: form.city.trim() }
          : { city: null, city_id: null }
    try {
      const updated = await usersApi.updateMe({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        ...cityFields,
        gender: form.gender || null,
        birthday: form.birthday || null,
        phone: form.phone.trim() || null,
        running_club: noClub ? '' : club.trim() || null,
        prior_experience: form.prior_experience || null,
        parent_first_name: form.parent_first_name.trim() || null,
        parent_last_name: form.parent_last_name.trim() || null,
        parent_phone: form.parent_phone.trim() || null,
      })
      onSaved(updated)
      setSaved(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить изменения')
    } finally {
      setLoading(false)
    }
  }

  const showClaimSearch =
    (form.prior_experience === 'once' || form.prior_experience === 'multiple') &&
    !hasApprovedClaim

  // Frozen server-side too (see PATCH /users/me) — disabling it here is
  // just so the form doesn't lie about being editable; switching the
  // answer after the fact would let someone dodge the newbie survey.
  const priorExperienceLocked = user?.prior_experience != null

  // Mirrors the backend's gate (profile_completeness_service) — highlighted
  // live off the current form state, so the field clears the moment it's
  // filled in, before the user even hits "Сохранить".
  const REQUIRED_HINT = 'Нужно для открытия рейтинга и статистики'
  // Under-14 runners must add a guardian's contacts (mirrors the backend gate).
  const age = ageFromISO(form.birthday)
  const isMinor = age != null && age < 14
  // Live, same as the fields above — no need to wait for "Сохранить" (or a
  // round trip to validate_birthday on the backend) to flag it.
  const futureBirthdayError =
    form.birthday && form.birthday > new Date().toISOString().slice(0, 10)
      ? 'Дата рождения не может быть в будущем'
      : null
  const missing = {
    city: !form.city.trim(),
    gender: !form.gender,
    birthday: !form.birthday,
    phone: !form.phone.trim(),
    runningClub: !noClub && !club.trim(),
    priorExperience: !form.prior_experience,
    avatar: !user?.avatar_url,
    parentFirstName: isMinor && !form.parent_first_name.trim(),
    parentLastName: isMinor && !form.parent_last_name.trim(),
    parentPhone: isMinor && !form.parent_phone.trim(),
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="card max-w-2xl space-y-5 p-6 sm:p-8">
        <div className="flex items-center gap-2 text-ink-600">
          <IconUser width={18} height={18} className="text-signal" />
          <h3 className="font-display text-lg text-ink">Личные данные</h3>
        </div>
        <FormError message={error} />
        {user?.needs_reentry && (
          <div className="rounded-xl2 border border-signal/30 bg-signal-wash px-4 py-3 text-sm text-ink-700">
            {user.pending_review ? (
              <>
                <strong className="text-signal-600">Имя ждёт подтверждения.</strong>{' '}
                Администратор проверит его в ближайшее время — до этого оно не показывается
                остальным участникам.
              </>
            ) : (
              <>
                <strong className="text-signal-600">Внесите реальные данные.</strong>{' '}
                Имя, указанное при регистрации, не прошло проверку — заполните заново и
                сохраните.
              </>
            )}
          </div>
        )}
        {!user?.needs_reentry && user?.pending_review && (
          <div className="rounded-xl2 border border-ink/10 bg-paper-soft px-4 py-3 text-sm text-ink-700">
            <strong className="text-ink">На модерации.</strong> Изменения ниже применятся после
            проверки администратором — до этого остальные участники видят прежние значения:
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
              {Object.entries(user.pending_review.changes)
                .filter(([field]) => field !== 'city_id') // "city" already names it
                .map(([field, value]) => (
                  <li key={field}>
                    {FIELD_LABELS[field] ?? field}:{' '}
                    <span className="font-medium">{formatPendingValue(field, value)}</span>
                  </li>
                ))}
            </ul>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Имя *"
            name="first_name"
            maxLength={NAME_MAX_LENGTH}
            value={form.first_name}
            onChange={setName('first_name')}
            error={fieldErrors.first_name}
            required
          />
          <Field
            label="Фамилия *"
            name="last_name"
            maxLength={NAME_MAX_LENGTH}
            value={form.last_name}
            onChange={setName('last_name')}
            error={fieldErrors.last_name}
            required
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <CityAutocomplete
            value={form.city}
            error={missing.city ? REQUIRED_HINT : undefined}
            onSelect={(c) => {
              setForm((f) => ({ ...f, city: c?.name ?? '', city_id: c?.id ?? null }))
              setSaved(false)
            }}
          />
          <SelectField
            label="Пол"
            name="gender"
            value={form.gender}
            onChange={set('gender')}
            error={missing.gender ? REQUIRED_HINT : undefined}
          >
            <option value="">Не указан</option>
            <option value="male">Мужской</option>
            <option value="female">Женский</option>
          </SelectField>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Дата рождения"
            name="birthday"
            type="date"
            max={new Date().toISOString().slice(0, 10)}
            value={form.birthday ?? ''}
            onChange={set('birthday')}
            error={futureBirthdayError ?? (missing.birthday ? REQUIRED_HINT : undefined)}
          />
          <Field
            label="Телефон"
            name="phone"
            type="tel"
            inputMode="tel"
            placeholder="+7 (___) ___-__-__"
            value={form.phone}
            onChange={(e) => {
              setForm((f) => ({ ...f, phone: nextRuPhoneValue(f.phone, e.target.value) }))
              setSaved(false)
            }}
            error={missing.phone ? REQUIRED_HINT : undefined}
          />
        </div>

        {isMinor && (
          <div className="space-y-4 rounded-xl2 border border-signal/25 bg-signal-wash/30 p-4">
            <p className="text-sm font-semibold text-ink">
              Данные родителя — для участников младше 14 лет
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Имя родителя"
                name="parent_first_name"
                maxLength={NAME_MAX_LENGTH}
                value={form.parent_first_name}
                onChange={setName('parent_first_name')}
                error={fieldErrors.parent_first_name || (missing.parentFirstName ? REQUIRED_HINT : undefined)}
              />
              <Field
                label="Фамилия родителя"
                name="parent_last_name"
                maxLength={NAME_MAX_LENGTH}
                value={form.parent_last_name}
                onChange={setName('parent_last_name')}
                error={fieldErrors.parent_last_name || (missing.parentLastName ? REQUIRED_HINT : undefined)}
              />
            </div>
            <Field
              label="Телефон родителя"
              name="parent_phone"
              type="tel"
              inputMode="tel"
              placeholder="+7 (___) ___-__-__"
              value={form.parent_phone}
              onChange={(e) => {
                setForm((f) => ({
                  ...f,
                  parent_phone: nextRuPhoneValue(f.parent_phone, e.target.value),
                }))
                setSaved(false)
              }}
              error={missing.parentPhone ? REQUIRED_HINT : undefined}
            />
          </div>
        )}

        <div>
          <label className={`field-label ${missing.runningClub ? 'text-danger-600' : ''}`}>
            Беговой клуб
          </label>
          <RunningClubField
            value={club}
            disabled={noClub}
            invalid={missing.runningClub}
            placeholder="Например, «DАЙ ХАРD Чебоксары»"
            onChange={(v) => {
              setClub(v)
              setSaved(false)
            }}
          />
          <label className="mt-2 flex items-center gap-2 text-sm text-ink-600">
            <input
              type="checkbox"
              checked={noClub}
              onChange={(e) => {
                setNoClub(e.target.checked)
                setSaved(false)
              }}
            />
            Не состою в беговом клубе
          </label>
          {missing.runningClub && <p className="mt-1.5 text-xs text-danger-600">{REQUIRED_HINT}</p>}
        </div>
        {!hasApprovedClaim && (
          <div>
            <SelectField
              label="Бегали ли вы раньше с DАЙ ХАРD?"
              name="prior_experience"
              value={form.prior_experience}
              onChange={set('prior_experience')}
              disabled={priorExperienceLocked}
              error={missing.priorExperience ? REQUIRED_HINT : undefined}
            >
              <option value="">Не указано</option>
              <option value="never">Нет, ни разу</option>
              <option value="once">Да, один раз</option>
              <option value="multiple">Да, несколько раз</option>
            </SelectField>
            {priorExperienceLocked && (
              <p className="mt-1.5 text-xs text-clay">
                Ответ фиксируется один раз и не может быть изменён.
              </p>
            )}
          </div>
        )}
        <p className="text-xs text-clay">
          Город, пол, дата рождения, телефон и беговой клуб видны только вам. В публичном профиле
          показываются имя, аватар, рейтинг и история участий. Рейтинг и статистика других
          участников открываются только после заполнения профиля на 100%.
        </p>
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? <Spinner className="h-5 w-5" /> : 'Сохранить'}
        </button>
        <FormSuccess message={saved ? 'Изменения сохранены' : null} />
      </form>

      {showClaimSearch && (
        <div>
          <h3 className="font-display text-lg text-ink">Похоже, вы уже бегали с нами</h3>
          <p className="mt-1 text-sm text-ink-600">
            Найдите себя в списке ниже — так мы перенесём ваши прошлые результаты на этот аккаунт.
          </p>
          <div className="mt-4">
            <GuestClaimSection />
          </div>
        </div>
      )}
    </div>
  )
}

function PasswordForm() {
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(false)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }))
    setDone(false)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const errs: Record<string, string> = {}
    const passErr = passwordError(form.new_password)
    if (passErr) errs.new_password = passErr
    if (!passErr && form.new_password !== form.confirm) errs.confirm = 'Пароли не совпадают'
    setFieldErrors(errs)
    if (Object.keys(errs).length > 0) return
    setLoading(true)
    try {
      await usersApi.changePassword({
        current_password: form.current_password,
        new_password: form.new_password,
      })
      setDone(true)
      setForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 400 || err.status === 401
            ? 'Текущий пароль указан неверно'
            : err.message
          : 'Не удалось изменить пароль',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-5 p-6 sm:p-8">
      <h3 className="font-display text-lg">Смена пароля</h3>
      <FormError message={error} />
      <FormSuccess message={done ? 'Пароль обновлён' : null} />
      <PasswordField
        label="Текущий пароль"
        name="current_password"
        autoComplete="current-password"
        value={form.current_password}
        onChange={set('current_password')}
        required
      />
      <PasswordField
        label="Новый пароль"
        name="new_password"
        autoComplete="new-password"
        placeholder={PASSWORD_HINT}
        value={form.new_password}
        onChange={set('new_password')}
        error={fieldErrors.new_password}
        required
      />
      <PasswordField
        label="Повторите новый пароль"
        name="confirm"
        autoComplete="new-password"
        value={form.confirm}
        onChange={set('confirm')}
        error={fieldErrors.confirm}
        required
      />
      <button type="submit" disabled={loading} className="btn-ink">
        {loading ? <Spinner className="h-5 w-5" /> : 'Обновить пароль'}
      </button>
    </form>
  )
}

function DataExportCard() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const download = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await usersApi.exportMe()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dh-data-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось выгрузить данные')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card p-6">
      <h3 className="font-display text-lg">Мои данные</h3>
      <p className="mt-2 text-sm text-ink-600">
        Скачайте всё, что о вас хранит платформа: профиль, историю участий и записи на группы
        — в формате JSON.
      </p>
      <FormError message={error} />
      <button onClick={download} disabled={loading} className="btn-ghost mt-4">
        {loading ? <Spinner className="h-5 w-5" /> : 'Скачать мои данные'}
      </button>
    </div>
  )
}

function DeleteAccountCard() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await usersApi.deleteMe(password)
      logout()
      navigate('/events', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 400
            ? 'Неверный пароль'
            : err.message
          : 'Не удалось удалить аккаунт',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card border-signal/20 p-6">
      <h3 className="font-display text-lg text-signal-600">Удаление аккаунта</h3>
      <p className="mt-2 text-sm text-ink-600">
        Аккаунт удаляется безвозвратно вместе с email, телефоном и остальными личными
        данными. Записи об участии в прошедших тренировках сохраняются в протоколе, но
        отвязываются от вас — подробнее в{' '}
        <Link to="/privacy-policy" className="font-semibold text-signal hover:underline">
          политике обработки персональных данных
        </Link>
        .
      </p>
      {!confirming ? (
        <button onClick={() => setConfirming(true)} className="btn-ghost mt-4 text-signal-600">
          Удалить аккаунт
        </button>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-3">
          <FormError message={error} />
          <input
            type="password"
            autoComplete="current-password"
            placeholder="Введите пароль для подтверждения"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field"
            required
          />
          <div className="flex gap-2">
            <button type="submit" disabled={loading || !password} className="btn-primary btn-sm">
              {loading ? <Spinner className="h-4 w-4" /> : 'Подтвердить удаление'}
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirming(false)
                setPassword('')
                setError(null)
              }}
              className="btn-ghost btn-sm"
            >
              Отмена
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

function claimStatusLabel(status: GuestClaim['status']) {
  if (status === 'approved') return { text: 'Подтверждено', cls: 'bg-ink text-paper' }
  if (status === 'rejected') return { text: 'Отклонено', cls: 'bg-ink/10 text-ink-600' }
  return { text: 'На рассмотрении', cls: 'bg-signal-wash text-signal-600' }
}

function GuestClaimSection() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<GuestProfile[]>([])
  const [searching, setSearching] = useState(false)
  const [claimedIds, setClaimedIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const myClaims = useAsync(() => guestsApi.myClaims(), [])

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      return
    }
    let active = true
    setSearching(true)
    const timer = setTimeout(() => {
      guestsApi
        .search(q)
        .then((r) => {
          if (active) setResults(r)
        })
        .catch(() => {
          if (active) setResults([])
        })
        .finally(() => {
          if (active) setSearching(false)
        })
    }, 300)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [query])

  const claim = async (guest: GuestProfile) => {
    setError(null)
    try {
      await guestsApi.claim(guest.id)
      setClaimedIds((prev) => new Set(prev).add(guest.id))
      myClaims.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить заявку')
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card p-6 sm:p-8">
        <p className="text-sm text-ink-600">
          Если организаторы загрузили список пробежавших до того, как вы зарегистрировались,
          ваш результат мог попасть в систему как гостевой профиль. Найдите себя по имени и
          заявите — администратор подтвердит и перенесёт результаты на ваш аккаунт.
        </p>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Введите имя или фамилию"
          className="mt-4 w-full rounded-lg border border-ink/15 px-3 py-2 text-sm"
        />
        <FormError message={error} />
        <div className="mt-4 space-y-2">
          {searching && (
            <div className="flex justify-center py-4">
              <Spinner className="text-signal" />
            </div>
          )}
          {!searching && query.trim().length >= 2 && results.length === 0 && (
            <p className="text-sm text-ink-600">Никого не нашли.</p>
          )}
          {results.map((g) => {
            const already = claimedIds.has(g.id)
            return (
              <div
                key={g.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-ink/[0.08] bg-white p-3"
              >
                <span className="flex min-w-0 items-center gap-3">
                  <Avatar first={g.first_name} last={g.last_name} src={g.avatar_url} size="sm" zoomable />
                  <span className="truncate font-semibold text-ink">
                    {g.first_name} {g.last_name}
                  </span>
                </span>
                <button
                  onClick={() => claim(g)}
                  disabled={already}
                  className={`shrink-0 ${already ? 'btn-ghost btn-sm' : 'btn-primary btn-sm'}`}
                >
                  {already ? 'Заявка отправлена' : 'Это я'}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <div className="card p-6 sm:p-8">
        <h3 className="font-display text-lg text-ink">Мои заявки</h3>
        {myClaims.loading ? (
          <div className="flex justify-center py-6">
            <Spinner className="text-signal" />
          </div>
        ) : myClaims.data?.length ? (
          <ul className="mt-4 space-y-2">
            {myClaims.data.map((c) => {
              const label = claimStatusLabel(c.status)
              return (
                <li
                  key={c.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-ink/[0.08] bg-white p-3"
                >
                  <span className="min-w-0 truncate font-semibold text-ink">
                    {c.guest.first_name} {c.guest.last_name}
                  </span>
                  <span className={`chip shrink-0 ${label.cls}`}>{label.text}</span>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-ink-600">Заявок пока нет.</p>
        )}
      </div>
    </div>
  )
}
