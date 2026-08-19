import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // The default auto-injected registerSW.js is a dumb
      // `navigator.serviceWorker.register(...)` with no update/reload logic —
      // src/pwa.ts registers through `virtual:pwa-register` instead, so it
      // can force a stale open tab to reload once a new service worker takes
      // over (see that file for why). Opting out of the auto-injected script
      // also opts out of vite-plugin-pwa's registerType-based default of
      // `workbox.skipWaiting`/`clientsClaim` (it only applies those
      // defaults when injectRegister is left at 'auto'), so they're set
      // explicitly below instead.
      injectRegister: false,
      includeAssets: ['favicon.png', 'apple-touch-icon.png'],
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
        // Without this, the service worker's navigation fallback intercepts
        // *every* full-page navigation — including /admin-tools and /admin,
        // which are server-rendered (SQLAdmin/Jinja), not part of this SPA —
        // and serves the cached index.html instead, which React Router then
        // 404s on since no client route matches. /api and /media are real
        // backend responses too, excluded for the same reason even though
        // those are normally fetch()ed rather than navigated to.
        navigateFallbackDenylist: [/^\/admin/, /^\/api/, /^\/media/],
      },
      manifest: {
        lang: 'ru',
        name: 'DАЙ ХАРD — беговое сообщество',
        short_name: 'DАЙ ХАРD',
        description:
          'Беговое сообщество Чебоксар — события, протоколы забегов, маршруты и рейтинг участников.',
        // Events is the actual landing page (see App.tsx's index redirect) — opening
        // straight there avoids an extra client-side redirect right after launch.
        start_url: '/events',
        scope: '/',
        display: 'standalone',
        background_color: '#F6F6F5',
        theme_color: '#0E0E0D',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          {
            src: '/pwa-maskable-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
  optimizeDeps: {
    // MapLibre ships a bundled web worker that Vite's dependency pre-bundler
    // mishandles (it looks for a non-existent maplibre-gl-worker.mjs and breaks
    // the whole app in dev). Serving it as native ESM instead avoids that.
    exclude: ['maplibre-gl'],
  },
  // MapLibre creates its worker with { type: 'module' }, so the worker Vite
  // bundles for it (see mapStyle.ts) must be an ES module too.
  worker: { format: 'es' },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Bind-mounted source on Windows/Docker Desktop doesn't reliably deliver
    // inotify events into the container, so chokidar's default watcher misses
    // host-side edits — fall back to polling so HMR/dev rebuilds actually fire.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
})
