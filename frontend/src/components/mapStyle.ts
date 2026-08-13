import { setWorkerUrl } from 'maplibre-gl'
import type { StyleSpecification } from 'maplibre-gl'
// maplibre-gl loads its worker via a dynamic URL that Vite can't emit in the
// production build — the file 404s and the map's render worker fails. Point it
// at a worker Vite bundles itself (?worker&url → emitted, hashed, served as
// plain .js), so it works the same in dev and prod.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

setWorkerUrl(maplibreWorkerUrl)

// Raster OpenStreetMap base — the same tiles the map used before, now rendered
// by MapLibre GL (no Leaflet). OSM is a global community project; only the JS
// library changed.
export const OSM_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: [
        'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}
