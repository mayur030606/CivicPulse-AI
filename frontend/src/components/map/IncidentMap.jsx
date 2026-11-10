import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import { formatDate } from '../../lib/format.js'

export default function IncidentMap({
  markers = [],
  center = [23.0225, 72.5714],
  zoom = 12,
}) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      scrollWheelZoom
      className="h-full w-full rounded-xl"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {markers.map((marker, index) => (
        <CircleMarker
          key={marker.id ?? marker.trackingId ?? index}
          center={[marker.latitude, marker.longitude]}
          radius={9}
          pathOptions={{
            color: marker.severityColor,
            fillColor: marker.severityColor,
            fillOpacity: 0.7,
            weight: 2,
          }}
        >
          <Popup>
            <div className="space-y-1 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Tracking ID
              </p>
              <p className="font-mono text-sm font-semibold text-slate-900">
                {marker.trackingId || '—'}
              </p>
              <p>
                <span className="font-semibold">Category:</span>{' '}
                {marker.categoryLabel}
              </p>
              <p>
                <span className="font-semibold">Status:</span>{' '}
                {marker.statusLabel}
              </p>
              <p>
                <span className="font-semibold">Severity:</span>{' '}
                {marker.severityLabel}
              </p>
              <p>
                <span className="font-semibold">Priority:</span>{' '}
                {marker.priorityLabel}
              </p>
              <p>
                <span className="font-semibold">Reported:</span>{' '}
                {formatDate(marker.createdAt)}
              </p>
              <p className="pt-1 text-slate-700">
                {marker.description || 'No description provided.'}
              </p>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
