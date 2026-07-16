interface PagerProps {
  page: number
  totalPages: number
  onChange: (page: number) => void
}

export function Pager({ page, totalPages, onChange }: PagerProps) {
  if (totalPages <= 1) return null
  return (
    <div className="mt-8 flex items-center justify-center gap-4">
      <button
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        className="btn-ghost btn-sm disabled:pointer-events-none disabled:opacity-40"
      >
        ← Назад
      </button>
      <span className="font-mono text-xs tabular text-clay">
        Страница {page} из {totalPages}
      </span>
      <button
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        className="btn-ghost btn-sm disabled:pointer-events-none disabled:opacity-40"
      >
        Вперёд →
      </button>
    </div>
  )
}
