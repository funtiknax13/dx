import { useMemo } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { TrackPoint } from '../types'

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap()
  useMemo(() => {
    if (bounds) {
      map.fitBounds(bounds, { padding: [24, 24] })
    }
  }, [bounds, map])
  return null
}

export function RouteMap({ points, className = '' }: { points: TrackPoint[]; className?: string }) {
  const path = useMemo<LatLngExpression[]>(
    () => points.map((p) => [p.lat, p.lng] as LatLngExpression),
    [points],
  )

  const bounds = useMemo<LatLngBoundsExpression | null>(() => {
    if (!points.length) return null
    const lats = points.map((p) => p.lat)
    const lngs = points.map((p) => p.lng)
    return [
      [Math.min(...lats), Math.min(...lngs)],
      [Math.max(...lats), Math.max(...lngs)],
    ]
  }, [points])

  if (!points.length) return null

  const start = path[0]
  const finish = path[path.length - 1]
  const center = start

  return (
    <div className={`overflow-hidden rounded-xl2 border border-ink/[0.08] shadow-card ${className}`}>
      <MapContainer
        center={center}
        zoom={13}
        scrollWheelZoom={false}
        style={{ height: '100%', width: '100%', minHeight: 320 }}
        attributionControl
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {/* black casing + white inner line — reads as a track marking on any tile set */}
        <Polyline positions={path} pathOptions={{ color: '#0E0E0D', weight: 7, opacity: 0.9 }} />
        <Polyline positions={path} pathOptions={{ color: '#F7F7F5', weight: 3, opacity: 1 }} />
        {/* start = hollow, finish = solid — distinguishable without color */}
        <CircleMarker
          center={start}
          radius={7}
          pathOptions={{ color: '#0E0E0D', weight: 2, fillColor: '#F7F7F5', fillOpacity: 1 }}
        >
          <Tooltip direction="top">Старт</Tooltip>
        </CircleMarker>
        <CircleMarker
          center={finish}
          radius={7}
          pathOptions={{ color: '#0E0E0D', weight: 2, fillColor: '#0E0E0D', fillOpacity: 1 }}
        >
          <Tooltip direction="top">Финиш</Tooltip>
        </CircleMarker>
        <FitBounds bounds={bounds} />
      </MapContainer>
    </div>
  )
}
