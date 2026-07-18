import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

export function LocationMap({
  lat,
  lng,
  label,
  className = '',
}: {
  lat: number
  lng: number
  label?: string
  className?: string
}) {
  return (
    <div className={`overflow-hidden rounded-xl2 border border-ink/[0.08] shadow-card ${className}`}>
      <MapContainer
        center={[lat, lng]}
        zoom={14}
        scrollWheelZoom={false}
        style={{ height: '100%', width: '100%', minHeight: 180 }}
        attributionControl
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <CircleMarker
          center={[lat, lng]}
          radius={9}
          pathOptions={{ color: '#0E0E0D', weight: 2, fillColor: '#0E0E0D', fillOpacity: 1 }}
        >
          {label && (
            <Tooltip direction="top" permanent>
              {label}
            </Tooltip>
          )}
        </CircleMarker>
      </MapContainer>
    </div>
  )
}
