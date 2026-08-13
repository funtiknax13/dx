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
  formatRuPhone,
  formatTime,
  fullName,
  ruPhoneDigits,
} from '../lib/format'
import { Avatar } from '../components/ui/Avatar'
import { AvatarCropModal } from '../components/AvatarCropModal'
import { Field, PasswordField, SelectField } from '../components/ui/Field'
import { CityAutocomplete } from '../components/ui/CityAutocomplete'
import { RunningClubField } from '../components/ui/RunningClubField'
import { Spinner } from '../components/ui/Spinner'
import { FormError, FormSuccess } from '../components/AuthShell'
import { IconArrow, IconCalendar, IconUser } from '../components/ui/icons'
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
        <div className="flex items-center gap-5">
          <AvatarUploader />
          <div>
            <h1 className="font-display text-2xl sm:text-3xl">
              {fullName(user.first_name, user.last_name)}
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
  onSubmitted,
}: {
  entries: AwaitingResultEntry[]
  onSubmitted: () => void
}) {
  return (
    <ul className="space-y-3">
      {entries.map((e) => (
        <AwaitingResultRow key={e.group_id} entry={e} onSubmitted={onSubmitted} />
      ))}
    </ul>
  )
}

function AwaitingResultRow({
  entry: e,
  onSubmitted,
}: {
  entry: AwaitingResultEntry
  onSubmitted: () => void
}) {
  const [open, setOpen] = useState(false)
  const pending = e.moderation_status === 'pending'
  const rejected = e.moderation_status === 'rejected'

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
          className={missing ? 'ring-2 ring-signal ring-offset-2' : ''}
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
        <p className="mt-1.5 max-w-[6rem] text-center text-[0.65rem] text-signal-600">
          Нужно для рейтинга
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
  const [form, setForm] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    city: user?.city ?? '',
    city_id: user?.city_id ?? null,
    gender: (user?.gender ?? '') as Gender | '',
    birthday: user?.birthday ?? '',
    phone: user?.phone ?? '',
    prior_experience: (user?.prior_experience ?? '') as PriorExperience | '',
    parent_first_name: user?.parent_first_name ?? '',
    parent_last_name: user?.parent_last_name ?? '',
    parent_phone: user?.parent_phone ?? '',
  })
  // Running club gets its own tri-state: text vs "not in a club" checkbox vs
  // untouched — see profile_completeness_service on the backend for why "" and
  // null mean different things here.
  const [noClub, setNoClub] = useState(user?.running_club === '')
  const [club, setClub] = useState(user?.running_club || '')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(false)

  const set =
    (k: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setForm((f) => ({ ...f, [k]: e.target.value }))
      setSaved(false)
    }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!form.first_name.trim() || !form.last_name.trim()) {
      setError('Имя и фамилия обязательны')
      return
    }
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
    // City: a canonical pick sends city_id (server mirrors the name); a legacy
    // free-text value with no id is kept as text; empty clears both.
    const cityFields: Pick<UpdateProfilePayload, 'city' | 'city_id'> =
      form.city_id != null
        ? { city_id: form.city_id }
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
        <FormSuccess message={saved ? 'Изменения сохранены' : null} />

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Имя *" name="first_name" value={form.first_name} onChange={set('first_name')} required />
          <Field label="Фамилия *" name="last_name" value={form.last_name} onChange={set('last_name')} required />
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
            error={missing.birthday ? REQUIRED_HINT : undefined}
          />
          <Field
            label="Телефон"
            name="phone"
            type="tel"
            inputMode="tel"
            placeholder="+7 (___) ___-__-__"
            value={form.phone}
            onChange={(e) => {
              setForm((f) => ({ ...f, phone: formatRuPhone(e.target.value) }))
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
                value={form.parent_first_name}
                onChange={set('parent_first_name')}
                error={missing.parentFirstName ? REQUIRED_HINT : undefined}
              />
              <Field
                label="Фамилия родителя"
                name="parent_last_name"
                value={form.parent_last_name}
                onChange={set('parent_last_name')}
                error={missing.parentLastName ? REQUIRED_HINT : undefined}
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
                setForm((f) => ({ ...f, parent_phone: formatRuPhone(e.target.value) }))
                setSaved(false)
              }}
              error={missing.parentPhone ? REQUIRED_HINT : undefined}
            />
          </div>
        )}

        <div>
          <label className={`field-label ${missing.runningClub ? 'text-signal-600' : ''}`}>
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
          {missing.runningClub && <p className="mt-1.5 text-xs text-signal-600">{REQUIRED_HINT}</p>}
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
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(false)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }))
    setDone(false)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (form.new_password.length < 8) {
      setError('Новый пароль — минимум 8 символов')
      return
    }
    if (form.new_password !== form.confirm) {
      setError('Пароли не совпадают')
      return
    }
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
        value={form.new_password}
        onChange={set('new_password')}
        required
      />
      <PasswordField
        label="Повторите новый пароль"
        name="confirm"
        autoComplete="new-password"
        value={form.confirm}
        onChange={set('confirm')}
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
                className="flex items-center justify-between rounded-xl border border-ink/[0.08] bg-white p-3"
              >
                <span className="flex items-center gap-3">
                  <Avatar first={g.first_name} last={g.last_name} src={g.avatar_url} size="sm" zoomable />
                  <span className="font-semibold text-ink">
                    {g.first_name} {g.last_name}
                  </span>
                </span>
                <button
                  onClick={() => claim(g)}
                  disabled={already}
                  className={already ? 'btn-ghost btn-sm' : 'btn-primary btn-sm'}
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
                  className="flex items-center justify-between rounded-xl border border-ink/[0.08] bg-white p-3"
                >
                  <span className="font-semibold text-ink">
                    {c.guest.first_name} {c.guest.last_name}
                  </span>
                  <span className={`chip ${label.cls}`}>{label.text}</span>
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
