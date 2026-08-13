import { useMemo } from 'react'
import { Layer, Map, Marker, Source } from 'react-map-gl/maplibre'
import type { Feature, LineString } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { TrackPoint } from '../types'
import { OSM_STYLE } from './mapStyle'

export function RouteMap({ points, className = '' }: { points: TrackPoint[]; className?: string }) {
  const line = useMemo<Feature<LineString>>(
    () => ({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: points.map((p) => [p.lng, p.lat]) },
      properties: {},
    }),
    [points],
  )

  const bounds = useMemo<[[number, number], [number, number]] | null>(() => {
    if (!points.length) return null
    const lats = points.map((p) => p.lat)
    const lngs = points.map((p) => p.lng)
    return [
      [Math.min(...lngs), Math.min(...lats)],
      [Math.max(...lngs), Math.max(...lats)],
    ]
  }, [points])

  if (!points.length) return null
  const start = points[0]
  const finish = points[points.length - 1]

  return (
    <div className={`overflow-hidden rounded-xl2 border border-ink/[0.08] shadow-card ${className}`}>
      <Map
        initialViewState={
          bounds
            ? { bounds, fitBoundsOptions: { padding: 24 } }
            : { longitude: start.lng, latitude: start.lat, zoom: 13 }
        }
        style={{ height: '100%', width: '100%', minHeight: 320 }}
        mapStyle={OSM_STYLE}
        scrollZoom={false}
        dragRotate={false}
      >
        {/* black casing + white inner line — reads as a track marking on any tiles */}
        <Source id="route" type="geojson" data={line}>
          <Layer
            id="route-casing"
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': '#0E0E0D', 'line-width': 7, 'line-opacity': 0.9 }}
          />
          <Layer
            id="route-line"
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': '#F7F7F5', 'line-width': 3 }}
          />
        </Source>
        {/* start = hollow, finish = solid — distinguishable without colour */}
        <Marker longitude={start.lng} latitude={start.lat} anchor="center">
          <span
            title="Старт"
            className="block h-3.5 w-3.5 rounded-full border-2 border-ink bg-paper"
          />
        </Marker>
        <Marker longitude={finish.lng} latitude={finish.lat} anchor="center">
          <span
            title="Финиш"
            className="block h-3.5 w-3.5 rounded-full border-2 border-paper bg-ink"
          />
        </Marker>
      </Map>
    </div>
  )
}
