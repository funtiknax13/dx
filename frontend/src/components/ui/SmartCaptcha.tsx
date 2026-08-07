import { useEffect, useRef } from 'react'

// Yandex SmartCaptcha widget API, loaded from their CDN on demand.
interface SmartCaptchaApi {
  render: (
    container: HTMLElement,
    params: { sitekey: string; hl?: string; callback?: (token: string) => void },
  ) => number
  destroy?: (widgetId: number) => void
  reset?: (widgetId?: number) => void
}

declare global {
  interface Window {
    smartCaptcha?: SmartCaptchaApi
  }
}

const SCRIPT_SRC = 'https://smartcaptcha.yandexcloud.net/captcha.js'
let scriptPromise: Promise<void> | null = null

function loadScript(): Promise<void> {
  if (window.smartCaptcha) return Promise.resolve()
  if (!scriptPromise) {
    scriptPromise = new Promise<void>((resolve, reject) => {
      const el = document.createElement('script')
      el.src = SCRIPT_SRC
      el.async = true
      el.defer = true
      el.onload = () => resolve()
      el.onerror = () => {
        scriptPromise = null
        reject(new Error('SmartCaptcha script failed to load'))
      }
      document.head.appendChild(el)
    })
  }
  return scriptPromise
}

interface Props {
  sitekey: string
  /** Called with the solved token; call with '' to signal it was cleared. */
  onToken: (token: string) => void
}

export function SmartCaptcha({ sitekey, onToken }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetIdRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    loadScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.smartCaptcha) return
        widgetIdRef.current = window.smartCaptcha.render(containerRef.current, {
          sitekey,
          hl: 'ru',
          callback: (token) => onToken(token),
        })
      })
      .catch(() => {
        /* network/adblock — the form still submits and the server decides */
      })
    return () => {
      cancelled = true
      if (widgetIdRef.current != null && window.smartCaptcha?.destroy) {
        window.smartCaptcha.destroy(widgetIdRef.current)
      }
      widgetIdRef.current = null
    }
  }, [sitekey, onToken])

  return <div ref={containerRef} className="min-h-[6rem]" />
}
