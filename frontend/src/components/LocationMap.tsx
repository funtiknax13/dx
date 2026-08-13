import { Map, Marker } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import { OSM_STYLE } from './mapStyle'

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
      <Map
        initialViewState={{ longitude: lng, latitude: lat, zoom: 14 }}
        style={{ height: '100%', width: '100%', minHeight: 180 }}
        mapStyle={OSM_STYLE}
        scrollZoom={false}
        dragRotate={false}
      >
        <Marker longitude={lng} latitude={lat} anchor="center">
          <div className="relative grid place-items-center">
            <span className="block h-[18px] w-[18px] rounded-full border-2 border-paper bg-ink" />
            {label && <span className="map-pin-label">{label}</span>}
          </div>
        </Marker>
      </Map>
    </div>
  )
}
