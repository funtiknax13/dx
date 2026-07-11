import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes } from 'react'

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

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  hint?: string
}

export function SelectField({ label, hint, id, children, ...rest }: SelectFieldProps) {
  const fieldId = id ?? rest.name
  return (
    <div>
      <label htmlFor={fieldId} className="field-label">
        {label}
      </label>
      <select id={fieldId} className="field appearance-none" {...rest}>
        {children}
      </select>
      {hint && <p className="mt-1.5 text-xs text-clay">{hint}</p>}
    </div>
  )
}
