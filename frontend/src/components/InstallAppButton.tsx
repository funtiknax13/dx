import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useInstallPrompt } from '../lib/useInstallPrompt'
import { IconDownload, IconShare, IconX } from './ui/icons'

/** Quiet, permanent "install the app" entry point for anyone who missed or
 * dismissed the browser's own one-shot install prompt. Renders nothing once
 * the app is already installed or on a browser that never offered install at
 * all. Android/desktop Chrome re-triggers the real native dialog; iOS Safari
 * has no such API (see useInstallPrompt), so it opens instructions instead. */
export function InstallAppButton({ className = '' }: { className?: string }) {
  const { canPrompt, showIosInstructions, promptInstall } = useInstallPrompt()
  const [showIosHelp, setShowIosHelp] = useState(false)

  if (!canPrompt && !showIosInstructions) return null

  return (
    <>
      <button
        type="button"
        onClick={canPrompt ? promptInstall : () => setShowIosHelp(true)}
        className={`inline-flex items-center gap-1.5 ${className}`}
      >
        <IconDownload width={14} height={14} />
        Установить приложение
      </button>
      {showIosHelp &&
        createPortal(
          <div
            className="fixed inset-0 z-50 grid place-items-center bg-ink/60 p-4"
            onClick={() => setShowIosHelp(false)}
          >
            <div
              className="relative w-full max-w-xs rounded-xl2 bg-white p-5 text-ink shadow-lift"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setShowIosHelp(false)}
                aria-label="Закрыть"
                className="absolute right-3 top-3 rounded-full p-1 text-clay transition hover:bg-ink/5 hover:text-ink"
              >
                <IconX width={16} height={16} />
              </button>
              <p className="pr-6 font-display text-lg">Установить на iPhone</p>
              <ol className="mt-3 space-y-3 text-left text-sm text-ink-600">
                <li className="flex items-center gap-2.5">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-paper-soft text-ink">
                    <IconShare width={15} height={15} />
                  </span>
                  Нажмите «Поделиться» внизу экрана Safari
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-paper-soft font-mono text-xs font-bold text-ink">
                    2
                  </span>
                  Выберите «На экран «Домой»»
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-paper-soft font-mono text-xs font-bold text-ink">
                    3
                  </span>
                  Подтвердите «Добавить»
                </li>
              </ol>
            </div>
          </div>,
          document.body,
        )}
    </>
  )
}
