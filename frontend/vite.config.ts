import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
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
