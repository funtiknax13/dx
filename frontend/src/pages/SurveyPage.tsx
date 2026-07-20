import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { surveysApi } from '../api/surveys'
import { ApiError } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { PageLoader } from '../components/ui/Spinner'
import { StatePanel } from '../components/ui/StatePanel'
import { FormError } from '../components/AuthShell'
import { IconSpark } from '../components/ui/icons'

export function SurveyPage() {
  const { data: survey, loading, error } = useAsync(() => surveysApi.active(), [])
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const returnTo = searchParams.get('from') || '/rating'

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!survey) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      await surveysApi.submit(
        survey.id,
        survey.questions.map((q) => ({ question_id: q.id, value: answers[q.id] ?? '' })),
      )
      navigate(returnTo, { replace: true })
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Не удалось отправить анкету')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <PageLoader />

  if (error || !survey) {
    // This page is only ever reached while locked for a survey reason (see
    // the rating/profile lock screens) — if there's nothing to fill out yet,
    // it's because the runner hasn't logged a first tracked run yet, not
    // because the survey doesn't apply to them.
    return (
      <div className="container-page py-16">
        <StatePanel
          title="Анкета появится после первой тренировки"
          description={
            error ??
            'Приходите на ближайший ДХ и дождитесь загрузки протокола — после этого здесь появится анкета, а после неё откроется рейтинг.'
          }
          icon={<IconSpark />}
          action={
            <Link to={returnTo} className="btn-ink">
              Назад
            </Link>
          }
        />
      </div>
    )
  }

  return (
    <div className="container-page max-w-2xl py-10 sm:py-14">
      <span className="eyebrow text-signal">
        <IconSpark width={16} height={16} /> Анкета новичка
      </span>
      <h1 className="mt-3 font-display text-3xl sm:text-4xl">{survey.title}</h1>
      {survey.description && <p className="mt-3 text-ink-600">{survey.description}</p>}
      <p className="mt-3 text-sm text-clay">
        Ответы видит только организатор — заполните, чтобы открыть рейтинг и статистику
        сообщества.
      </p>

      <form onSubmit={submit} className="card mt-8 space-y-6 p-6 sm:p-8">
        <FormError message={submitError} />
        {survey.questions.map((q, i) => (
          <div key={q.id}>
            <label htmlFor={`q-${q.id}`} className="field-label">
              {i + 1}. {q.prompt}
              {q.required && ' *'}
            </label>
            <textarea
              id={`q-${q.id}`}
              rows={3}
              required={q.required}
              value={answers[q.id] ?? ''}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
              className="field"
            />
          </div>
        ))}
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? 'Отправка…' : 'Отправить анкету'}
        </button>
      </form>
    </div>
  )
}
