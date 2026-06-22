const DOC_ICONS = {
  regulation: '⚖️',
  communal: '🏛️',
  norm: '📐',
  permit: '📋',
}

const DOC_LABELS = {
  regulation: 'Texte réglementaire',
  communal: 'Document communal',
  norm: 'Norme technique',
  permit: 'Autorisation',
}

function HeightVisual({ maxFloors }) {
  if (!maxFloors || maxFloors === 0) return null
  const floors = Math.min(maxFloors, 8)
  return (
    <div className="height-visual">
      {Array.from({ length: floors }).map((_, i) => (
        <div
          key={i}
          className="height-floor"
          style={{ height: `${((i + 1) / floors) * 100}%` }}
        />
      ))}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="section">
      <div className="section-title">{title}</div>
      {children}
    </div>
  )
}

export default function ZonePanel({ data }) {
  if (data.error) {
    return (
      <div className="empty-state">
        <p>{data.error}</p>
      </div>
    )
  }

  const { zone, rules, nq_pap_nearby, coordinates } = data
  const isNonBuildable = rules.height?.max_floors === 0

  return (
    <>
      <div
        className="zone-badge"
        style={{
          background: zone.color + '33',
          border: `1px solid ${zone.color}55`,
          color: zone.color,
        }}
      >
        {zone.categorie}
      </div>

      <div className="zone-name">{rules.name}</div>
      <div className="zone-density">{rules.density}</div>
      <div className="zone-description">{rules.description}</div>

      {isNonBuildable && (
        <div className="nq-pap-alert" style={{ marginBottom: 16, borderColor: '#ef4444', color: '#fca5a5', background: '#450a0a' }}>
          <strong>⛔ Zone non constructible</strong>
          Toute construction est interdite ou très fortement limitée dans cette zone.
        </div>
      )}

      {nq_pap_nearby.length > 0 && (
        <div className="nq-pap-alert" style={{ marginBottom: 16 }}>
          <strong>⚠️ Zone NQ-PAP à proximité</strong>
          {nq_pap_nearby.length} secteur(s) de nouveau quartier (PAP-NQ) détecté(s) dans un rayon de 500m. Des règles spécifiques de développement peuvent s'appliquer.
        </div>
      )}

      <div className="divider" />

      {rules.height?.max_floors > 0 && (
        <Section title="Gabarit autorisé">
          <HeightVisual maxFloors={rules.height.max_floors} />
          <div className="height-label">{rules.height.label}</div>
        </Section>
      )}

      {rules.pap_required && (
        <Section title="Procédure">
          <span className="pap-badge">
            📄 PAP requis · {rules.pap_type}
          </span>
        </Section>
      )}

      <Section title="Usages autorisés">
        {rules.allowed_uses.length > 0 ? (
          <div className="pill-list">
            {rules.allowed_uses.map(u => (
              <span key={u} className="pill pill-green">{u}</span>
            ))}
          </div>
        ) : (
          <span className="height-label">Voir règlement communal</span>
        )}
      </Section>

      {rules.forbidden_uses.length > 0 && (
        <Section title="Usages interdits">
          <div className="pill-list">
            {rules.forbidden_uses.map(u => (
              <span key={u} className="pill pill-red">{u}</span>
            ))}
          </div>
        </Section>
      )}

      <div className="divider" />

      {rules.seco_touchpoints.length > 0 && (
        <Section title="Points de contrôle SECO">
          <div className="seco-list">
            {rules.seco_touchpoints.map(t => (
              <div key={t} className="seco-item">
                <div className="seco-dot" />
                {t}
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Check-list pré-projet">
        <div className="checklist">
          {rules.checklist.map(item => {
            const isStop = item.startsWith('STOP') || item.startsWith('Non constructible')
            return (
              <div key={item} className={`checklist-item${isStop ? ' warn' : ''}`}>
                {isStop ? (
                  <svg className="check-icon" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 12A5 5 0 118 3a5 5 0 010 10zm-.75-8h1.5v4.5h-1.5V5zm0 5.5h1.5V12h-1.5v-1.5z"/>
                  </svg>
                ) : (
                  <svg className="check-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="2" y="2" width="12" height="12" rx="2" />
                  </svg>
                )}
                {item}
              </div>
            )
          })}
        </div>
      </Section>

      <div className="divider" />

      <Section title="Documents réglementaires">
        <div className="doc-list">
          {rules.documents.map(doc => (
            <a
              key={doc.title}
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="doc-item"
            >
              <div className={`doc-icon ${doc.type}`}>
                {DOC_ICONS[doc.type] || '📄'}
              </div>
              <div className="doc-content">
                <div className="doc-title">{doc.title}</div>
                <div className="doc-type">{DOC_LABELS[doc.type] || doc.type}</div>
                {doc.note && <div className="doc-note">{doc.note}</div>}
              </div>
            </a>
          ))}
        </div>
      </Section>

      <div className="coords">
        {coordinates.lat.toFixed(5)}°N, {coordinates.lng.toFixed(5)}°E
        {zone.nom_fichier && <> · {zone.nom_fichier}</>}
      </div>
    </>
  )
}
