import { forwardRef, useState, type InputHTMLAttributes, type SelectHTMLAttributes } from 'react'
import { IconEye, IconEyeOff } from './icons'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
  error?: string
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, hint, error, id, className = '', ...rest },
  ref,
) {
  const fieldId = id ?? rest.name
  return (
    <div>
      <label htmlFor={fieldId} className="field-label">
        {label}
      </label>
      <input
        id={fieldId}
        ref={ref}
        className={`field ${error ? 'border-signal ring-2 ring-signal/20' : ''} ${className}`}
        {...rest}
      />
      {error ? (
        <p className="mt-1.5 text-xs text-signal-600">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-clay">{hint}</p>
      ) : null}
    </div>
  )
})

type PasswordFieldProps = Omit<FieldProps, 'type'>

export const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(
  function PasswordField({ label, hint, error, id, className = '', ...rest }, ref) {
    const [visible, setVisible] = useState(false)
    const fieldId = id ?? rest.name
    return (
      <div>
        <label htmlFor={fieldId} className="field-label">
          {label}
        </label>
        <div className="relative">
          <input
            id={fieldId}
            ref={ref}
            type={visible ? 'text' : 'password'}
            className={`field pr-11 ${error ? 'border-signal ring-2 ring-signal/20' : ''} ${className}`}
            {...rest}
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="absolute inset-y-0 right-0 grid w-11 place-items-center text-clay transition hover:text-ink"
            aria-label={visible ? 'Скрыть пароль' : 'Показать пароль'}
          >
            {visible ? <IconEyeOff width={18} height={18} /> : <IconEye width={18} height={18} />}
          </button>
        </div>
        {error ? (
          <p className="mt-1.5 text-xs text-signal-600">{error}</p>
        ) : hint ? (
          <p className="mt-1.5 text-xs text-clay">{hint}</p>
        ) : null}
      </div>
    )
  },
)

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  hint?: string
  error?: string
}

export function SelectField({ label, hint, error, id, children, ...rest }: SelectFieldProps) {
  const fieldId = id ?? rest.name
  return (
    <div>
      <label htmlFor={fieldId} className="field-label">
        {label}
      </label>
      <select
        id={fieldId}
        className={`field appearance-none ${error ? 'border-signal ring-2 ring-signal/20' : ''}`}
        {...rest}
      >
        {children}
      </select>
      {error ? (
        <p className="mt-1.5 text-xs text-signal-600">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-clay">{hint}</p>
      ) : null}
    </div>
  )
}
