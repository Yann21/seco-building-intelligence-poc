import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import ZonePanel from './ZonePanel'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8001'

const LEGEND = [
  { color: '#fde68a', label: 'HAB 1 – Résidentiel faible densité' },
  { color: '#fbbf24', label: 'HAB 2 – Résidentiel moyen' },
  { color: '#f97316', label: 'MIX_u – Mixte urbain' },
  { color: '#fb923c', label: 'MIX_v – Mixte villageois' },
  { color: '#16a34a', label: 'FOR – Forestier' },
  { color: '#86efac', label: 'AGR – Agricole' },
  { color: '#60a5fa', label: 'BEP – Équipements publics' },
  { color: '#a7f3d0', label: 'VERD/PARC/JAR – Espaces verts' },
  { color: '#c084fc', label: 'ECO – Activités économiques' },
]

export default function App() {
  const mapRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const markerRef = useRef(null)
  const [zoneData, setZoneData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [mapLoading, setMapLoading] = useState(true)

  useEffect(() => {
    const map = L.map(mapRef.current, {
      center: [49.75, 6.17],
      zoom: 10,
      zoomControl: true,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap © CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map)

    mapInstanceRef.current = map

    const renderer = L.canvas({ padding: 0.5 })

    fetch(`${API_BASE}/api/geojson/zonage`)
      .then(r => r.json())
      .then(data => {
        L.geoJSON(data, {
          renderer,
          style: feat => ({
            color: feat.properties.color,
            fillColor: feat.properties.color,
            fillOpacity: 0.35,
            weight: 0.5,
            opacity: 0.6,
          }),
        }).addTo(map)

        fetch(`${API_BASE}/api/geojson/nq_pap`)
          .then(r => r.json())
          .then(nqData => {
            L.geoJSON(nqData, {
              renderer,
              style: {
                color: '#facc15',
                fillColor: '#facc15',
                fillOpacity: 0.25,
                weight: 1.5,
                opacity: 0.9,
                dashArray: '4 3',
              },
            }).addTo(map)
            setMapLoading(false)
          })
      })
      .catch(() => setMapLoading(false))

    map.on('click', async e => {
      const { lat, lng } = e.latlng

      if (markerRef.current) markerRef.current.remove()
      markerRef.current = L.circleMarker([lat, lng], {
        radius: 7,
        color: '#3b82f6',
        fillColor: '#3b82f6',
        fillOpacity: 0.9,
        weight: 2,
      }).addTo(map)

      setLoading(true)
      setZoneData(null)

      try {
        const res = await fetch(`${API_BASE}/api/zone?lat=${lat}&lng=${lng}`)
        if (!res.ok) {
          setZoneData({ error: 'Aucune zone trouvée à cet emplacement.' })
        } else {
          setZoneData(await res.json())
        }
      } catch {
        setZoneData({ error: 'Erreur de connexion au serveur.' })
      } finally {
        setLoading(false)
      }
    })

    return () => map.remove()
  }, [])

  return (
    <>
    <div className="app">
      <div className="map-container">
        <div ref={mapRef} style={{ height: '100%', width: '100%' }} />

        <div className="map-hint">
          Cliquez sur la carte pour analyser une zone PAG
        </div>

        {mapLoading && (
          <div className="map-loading-indicator">
            <div className="spinner" />
            Chargement des zones PAG…
          </div>
        )}

        <div className="legend">
          <div className="legend-title">Zones PAG</div>
          {LEGEND.map(item => (
            <div key={item.label} className="legend-item">
              <div className="legend-swatch" style={{ background: item.color }} />
              <span>{item.label}</span>
            </div>
          ))}
          <div className="legend-item" style={{ marginTop: 6 }}>
            <div className="legend-swatch" style={{ background: '#facc15', opacity: 0.7 }} />
            <span>NQ-PAP (zones en développement)</span>
          </div>
        </div>
      </div>

      <div className="sidebar">
        <div className="sidebar-header">
          <h1>PAG Insight</h1>
          <p>Zoning intelligence · Luxembourg</p>
        </div>
        <div className="sidebar-body">
          {loading ? (
            <div className="loading">
              <div className="spinner" />
              Analyse de la zone…
            </div>
          ) : zoneData ? (
            <ZonePanel data={zoneData} />
          ) : (
            <div className="empty-state">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
              <p>Cliquez sur la carte pour analyser une parcelle et voir les règles PAG applicables, les documents requis et les points de contrôle SECO.</p>
            </div>
          )}
        </div>
      </div>
    </div>
    <div className="credits-bar">
      Vision &amp; concept · <strong>Clément Gérard</strong> (M3) &nbsp;·&nbsp; Implémentation · <strong>Yann Hoffmann</strong>
    </div>
    </>
  )
}
