import { useEffect, useState } from 'react'
import { api } from './client'

export interface CaptchaConfig {
  enabled: boolean
  client_key: string | null
}

const DISABLED: CaptchaConfig = { enabled: false, client_key: null }

// Fetched once and reused — the config doesn't change within a session, and
// every auth/support form would otherwise re-request it.
let cached: Promise<CaptchaConfig> | null = null

export function getCaptchaConfig(): Promise<CaptchaConfig> {
  if (!cached) {
    cached = api
      .get<CaptchaConfig>('/auth/captcha-config', { auth: false })
      .catch(() => DISABLED)
  }
  return cached
}

/** Null while loading; then the resolved config. */
export function useCaptchaConfig(): CaptchaConfig | null {
  const [config, setConfig] = useState<CaptchaConfig | null>(null)
  useEffect(() => {
    let active = true
    getCaptchaConfig().then((c) => {
      if (active) setConfig(c)
    })
    return () => {
      active = false
    }
  }, [])
  return config
}
