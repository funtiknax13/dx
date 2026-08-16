import { useEffect, useState } from 'react'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

function isStandalone(): boolean {
  if (typeof window === 'undefined') return false
  return (
    window.matchMedia?.('(display-mode: standalone)').matches === true ||
    // iOS Safari's own flag — the standalone media query above doesn't cover it.
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

function isIos(): boolean {
  if (typeof navigator === 'undefined') return false
  return /iphone|ipad|ipod/i.test(navigator.userAgent) && !('MSStream' in window)
}

/** Wraps the browser's "add to home screen" flow so a button anywhere in the
 * UI (not just the browser's own one-shot mini-infobar, easy to miss or
 * dismiss by accident) can offer it on demand.
 *
 * - `canPrompt`: Android/desktop Chrome already handed us a deferred prompt —
 *   `promptInstall()` re-opens the real native install dialog.
 * - `showIosInstructions`: Safari has no programmatic install API at all (no
 *   browser exposes one for it) — the caller should show manual
 *   "Share -> On Home Screen" steps instead.
 * - Neither: nothing to offer (already installed, or an unsupported browser
 *   that hasn't fired the event — most likely just hasn't yet, e.g. before
 *   enough engagement; there's nothing to do but wait for it). */
export function useInstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [installed, setInstalled] = useState(isStandalone)

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault()
      setDeferred(e as BeforeInstallPromptEvent)
    }
    const onInstalled = () => {
      setInstalled(true)
      setDeferred(null)
    }
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const promptInstall = async () => {
    if (!deferred) return
    await deferred.prompt()
    await deferred.userChoice
    setDeferred(null)
  }

  return {
    canPrompt: !installed && deferred != null,
    showIosInstructions: !installed && isIos(),
    promptInstall,
  }
}
