export function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Загрузка"
      className={`inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-r-transparent align-[-0.125em] ${className}`}
    />
  )
}

export function PageLoader({ label = 'Загружаем…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-ink-600">
      <Spinner className="h-8 w-8 text-signal" />
      <p className="font-mono text-xs uppercase tracking-[0.2em]">{label}</p>
    </div>
  )
}
