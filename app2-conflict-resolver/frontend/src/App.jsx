import { useEffect, useState } from 'react'

const API = import.meta.env.VITE_API_BASE ?? 'http://localhost:8002'

const TYPE_LABELS = {
  contradiction: 'Contradiction directe',
  lacune: 'Lacune réglementaire',
  'ambiguïté': 'Ambiguïté terminologique',
  ambiguité: 'Ambiguïté terminologique',
}

function SeverityBadge({ severity }) {
  return <span className={`severity-badge ${severity}`}>{severity}</span>
}

function ConflictCard({ conflict, resolution, onResolve }) {
  const [open, setOpen] = useState(false)
  const [decision, setDecision] = useState('')
  const [expert, setExpert] = useState('Architecte')
  const isResolved = !!resolution

  return (
    <div className={`conflict-card ${isResolved ? 'resolved' : ''}`}>
      <div className="conflict-header" onClick={() => setOpen(o => !o)}>
        <SeverityBadge severity={conflict.severity} />
        <div className="conflict-title-block">
          <div className="conflict-title">{conflict.title}</div>
          <div className="conflict-type">
            {TYPE_LABELS[conflict.type] || conflict.type}
            {isResolved && <span className="resolved-tag" style={{ marginLeft: 8 }}>✓ Résolu</span>}
            {conflict.quote_verified === false && <span className="unverified-tag" title="La citation n'a pas pu être retrouvée dans le document source" style={{ marginLeft: 8 }}>⚠ citation non vérifiée</span>}
          </div>
        </div>
        <span className={`expand-icon ${open ? 'open' : ''}`}>›</span>
      </div>

      {open && (
        <div className="conflict-body">
          <p className="conflict-description">{conflict.description}</p>
          <div className="sources-grid">
            {conflict.sources.map((src, i) => (
              <div key={i} className="source-card">
                <div className="source-doc-id">{src.doc_id}</div>
                <div className="source-article">{src.article}</div>
                {src.value && <div className="source-value">→ {src.value}</div>}
                {src.quote && <div className="source-quote">"{src.quote}"</div>}
              </div>
            ))}
          </div>
          <div className="recommendation-box">
            <div className="label">Recommandation (principe de la valeur la plus contraignante)</div>
            <p>{conflict.recommendation}</p>
          </div>
          {conflict.practical_impact && (
            <div className="impact-box">
              <div className="label">Impact pratique</div>
              {conflict.practical_impact}
            </div>
          )}
          <div className="resolution-section">
            <div className="resolution-label">Décision experte</div>
            {isResolved ? (
              <div className="resolution-existing">
                <div>{resolution.decision}</div>
                <div className="resolution-meta">— {resolution.resolved_by} · {new Date(resolution.resolved_at).toLocaleDateString('fr-FR')}</div>
              </div>
            ) : (
              <div className="resolution-form">
                <textarea className="resolution-textarea" placeholder="Documenter la décision prise pour ce conflit…" value={decision} onChange={e => setDecision(e.target.value)} />
                <div className="resolution-footer">
                  <input className="resolution-name" placeholder="Nom de l'expert" value={expert} onChange={e => setExpert(e.target.value)} />
                  <button className="btn-resolve" disabled={!decision.trim()} onClick={() => onResolve(conflict.id, decision, expert)}>Valider la décision</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const CLUSTER_ICONS = {
  lighting:    '💡',
  ventilation: '🌬',
  ascenseurs:  '🛗',
  default:     '📁',
}

function ClusterSidebar({ docs, conflicts, selectedCluster, onSelect }) {
  // Build cluster map: { clusterName: { docs: [], conflictCount: N } }
  const normId = id => id?.replace(/\s+/g, '-')
  const docById = Object.fromEntries(Object.values(docs).map(d => [normId(d.id), d]))
  const clusters = {}
  Object.values(docs).forEach(doc => {
    const c = doc.cluster || 'default'
    if (!clusters[c]) clusters[c] = { docs: [], conflictIds: new Set() }
    clusters[c].docs.push(doc)
  })
  conflicts.forEach(conflict => {
    const srcDoc = docById[normId(conflict.sources?.[0]?.doc_id)]
    const c = srcDoc?.cluster || 'default'
    if (clusters[c]) clusters[c].conflictIds.add(conflict.id)
  })

  const totalConflicts = conflicts.length

  return (
    <div className="cluster-sidebar">
      <div className="cluster-sidebar-label">Corpus réglementaire</div>

      {/* All clusters row */}
      <div
        className={`cluster-row ${selectedCluster === null ? 'active' : ''}`}
        onClick={() => onSelect(null)}
      >
        <span className="cluster-icon">🗂</span>
        <span className="cluster-name">Tous les clusters</span>
        <span className="cluster-count">{totalConflicts}</span>
      </div>

      <div className="cluster-divider" />

      {Object.entries(clusters).map(([name, { docs: clusterDocs, conflictIds }]) => {
        const isSelected = selectedCluster === name
        const icon = CLUSTER_ICONS[name] || CLUSTER_ICONS.default
        return (
          <div key={name}>
            <div
              className={`cluster-row ${isSelected ? 'active' : ''}`}
              onClick={() => onSelect(isSelected ? null : name)}
            >
              <span className="cluster-icon">{icon}</span>
              <span className="cluster-name">{name}</span>
              <span className="cluster-count">{conflictIds.size}</span>
            </div>
            {isSelected && (
              <div className="cluster-docs">
                {clusterDocs.map(doc => (
                  <div key={doc.id} className="doc-card">
                    <div className="doc-card-id">{doc.id}</div>
                    <div className="doc-card-title">{doc.title}</div>
                    <div className="doc-card-meta">{doc.date}</div>
                    <a href={doc.url} target="_blank" rel="noopener noreferrer">↗ Source</a>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function App() {
  const [data, setData] = useState(null)
  const [resolutions, setResolutions] = useState({})
  const [loading, setLoading] = useState(true)
  const [dark, setDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  const [selectedCluster, setSelectedCluster] = useState(null)

  useEffect(() => {
    document.documentElement.classList.toggle('light', !dark)
  }, [dark])

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/conflicts`).then(r => r.json()),
      fetch(`${API}/api/resolutions`).then(r => r.json()),
    ]).then(([conflicts, res]) => {
      setData(conflicts)
      setResolutions(res)
      setLoading(false)
    })
  }, [])

  const handleResolve = async (conflictId, decision, resolvedBy) => {
    await fetch(`${API}/api/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conflict_id: conflictId, decision, resolved_by: resolvedBy }),
    })
    setResolutions(r => ({ ...r, [conflictId]: { decision, resolved_by: resolvedBy, resolved_at: new Date().toISOString() } }))
  }

  if (loading) {
    return <div className="loading-screen"><div className="spinner" />Chargement de l'analyse…</div>
  }

  const allConflicts = data.conflicts || []
  const docs = data.documents || {}
  // LLM sometimes outputs "ITM-CL 55.2" (space) vs stored "ITM-CL-55.2" (hyphen) — normalise both sides
  const normId = id => id?.replace(/\s+/g, '-')
  const docById = Object.fromEntries(Object.values(docs).map(d => [normId(d.id), d]))

  const conflicts = selectedCluster === null
    ? allConflicts
    : allConflicts.filter(c => {
        const srcDoc = docById[normId(c.sources?.[0]?.doc_id)]
        return (srcDoc?.cluster || 'default') === selectedCluster
      })

  const bySeverity = {
    critique: conflicts.filter(c => c.severity === 'critique').length,
    majeur: conflicts.filter(c => c.severity === 'majeur').length,
    mineur: conflicts.filter(c => c.severity === 'mineur').length,
  }
  const resolvedCount = Object.keys(resolutions).length

  return (
    <div className="app">
      <div className="header">
        <div className="header-left">
          <h1>Conflict Resolver</h1>
          <p>Analyse de conflits réglementaires · {selectedCluster ? selectedCluster : 'tous clusters'} · Luxembourg</p>
        </div>
        <div className="header-stats">
          {bySeverity.critique > 0 && <span className="stat-chip critique">⚠ {bySeverity.critique} critique{bySeverity.critique > 1 ? 's' : ''}</span>}
          {bySeverity.majeur > 0 && <span className="stat-chip majeur">↑ {bySeverity.majeur} majeur{bySeverity.majeur > 1 ? 's' : ''}</span>}
          {bySeverity.mineur > 0 && <span className="stat-chip mineur">· {bySeverity.mineur} mineur{bySeverity.mineur > 1 ? 's' : ''}</span>}
          {resolvedCount > 0 && <span className="stat-chip resolved">✓ {resolvedCount} résolu{resolvedCount > 1 ? 's' : ''}</span>}
          <button className="theme-toggle" onClick={() => setDark(d => !d)} aria-label="Toggle theme">
            <span className="theme-toggle-label">{dark ? '☀' : '☾'}</span>
            <div className={`toggle-track ${dark ? '' : 'on'}`}>
              <div className="toggle-thumb" />
            </div>
          </button>
        </div>
      </div>
      <div className="layout">
        <ClusterSidebar
          docs={docs}
          conflicts={allConflicts}
          selectedCluster={selectedCluster}
          onSelect={setSelectedCluster}
        />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {data.summary && <div className="summary-banner">{data.summary}</div>}
          <div className="conflicts-panel">
            <div className="conflicts-grid">
              {conflicts.map(conflict => (
                <ConflictCard key={conflict.id} conflict={conflict} resolution={resolutions[conflict.id]} onResolve={handleResolve} />
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="credits-bar">
        Vision &amp; concept · <strong>Clément Gérard</strong> (M3) &nbsp;·&nbsp; Implémentation · <strong>Yann Hoffmann</strong>
      </div>
    </div>
  )
}
