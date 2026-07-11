import { Link } from 'react-router-dom'
import { IconRunner } from '../components/ui/icons'

export function NotFoundPage() {
  return (
    <div className="container-page flex min-h-[60vh] flex-col items-center justify-center py-20 text-center">
      <div className="grid h-20 w-20 place-items-center rounded-2xl bg-ink text-volt">
        <IconRunner width={40} height={40} />
      </div>
      <p className="mt-8 font-mono text-sm uppercase tracking-[0.3em] text-signal">Ошибка 404</p>
      <h1 className="mt-3 font-display text-5xl sm:text-6xl">Сошли с дистанции</h1>
      <p className="mt-4 max-w-md text-ink-600">
        Такой страницы не существует или она была перемещена. Вернитесь на маршрут.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link to="/events" className="btn-primary btn-lg">
          К событиям
        </Link>
        <Link to="/rating" className="btn-ghost btn-lg">
          Рейтинг
        </Link>
      </div>
    </div>
  )
}
