import { useEffect, useRef } from 'react'
import 'altcha'
import { api } from '../../api/client'

interface Props {
  /** Called with the solved proof-of-work token; '' when cleared/expired. */
  onToken: (token: string) => void
}

/** Self-hosted Altcha widget — fetches a proof-of-work challenge from our own
 * backend, solves it in a worker, and reports the solution token. No external
 * service or keys. */
export function Altcha({ onToken }: Props) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onState = (e: Event) => {
      const detail = (e as CustomEvent<{ state?: string; payload?: string }>).detail
      if (detail?.state === 'verified' && detail.payload) onToken(detail.payload)
      else onToken('')
    }
    el.addEventListener('statechange', onState)
    return () => el.removeEventListener('statechange', onState)
  }, [onToken])

  return (
    <altcha-widget
      ref={ref}
      challengeurl={`${api.apiUrl}/auth/altcha-challenge`}
      strings={JSON.stringify({
        label: 'Я человек',
        verifying: 'Проверяем…',
        verified: 'Готово',
        error: 'Не удалось проверить — попробуйте ещё раз',
        expired: 'Проверка устарела, обновите страницу',
      })}
    />
  )
}
