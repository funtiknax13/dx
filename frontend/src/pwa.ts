import { registerSW } from 'virtual:pwa-register'

// registerType: 'autoUpdate' (vite.config.ts) only controls what's baked into
// the generated service worker (skipWaiting/clientsClaim) — it does not make
// an already-open tab reload itself. Without this registration, a tab left
// open across a deploy keeps running the old JS bundle, which can try to
// lazy-load a route chunk that `rsync --delete` (see DEPLOY.md) already
// removed from the server on the next deploy — the "works until you
// hard-refresh" bug. registerSW here is what actually reloads the page once
// a new version is ready.
const UPDATE_CHECK_INTERVAL = 60 * 60 * 1000

registerSW({
  immediate: true,
  onRegisteredSW(_url, registration) {
    if (!registration) return
    // A plain SW registration is only re-checked by the browser on a full
    // navigation — a single-page app left open for hours would otherwise
    // never notice a new deploy, since client-side routing never triggers
    // one.
    setInterval(() => {
      registration.update()
    }, UPDATE_CHECK_INTERVAL)
  },
})
