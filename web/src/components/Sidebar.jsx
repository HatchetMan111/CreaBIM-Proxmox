import { useMemo, useState } from 'react';
import { relativeTime } from '../format.js';

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 64 64" role="img" aria-label="CreaBIM">
      <rect width="64" height="64" rx="14" fill="#4F6B4C" />
      <text
        x="32"
        y="46"
        textAnchor="middle"
        fontFamily="Georgia, serif"
        fontSize="42"
        fill="#ffffff"
      >
        C
      </text>
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="search-icon">
      <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M13.2 13.2 17 17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export default function Sidebar({
  projects,
  selectedId,
  onSelect,
  onNew,
  onImport,
  health,
  info,
  open,
  onToggle,
}) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter((project) =>
      String(project.name || '').toLowerCase().includes(needle),
    );
  }, [projects, query]);

  const healthy = health?.status === 'ok';
  const healthClass = health ? (healthy ? 'is-ok' : 'is-bad') : 'is-pending';

  return (
    <>
      <div
        className={`sidebar-scrim ${open ? 'is-visible' : ''}`}
        onClick={onToggle}
        aria-hidden="true"
      />

      <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Projekt-Navigation">
        <div className="brand">
          <BrandMark />
          <div className="brand-row">
            <span className="brand-name">CreaBIM</span>
            <span className="badge badge-brand">Server</span>
          </div>
          <button
            type="button"
            className="icon-btn sidebar-close"
            onClick={onToggle}
            aria-label="Navigation schließen"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M5 5l10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="sidebar-actions">
          <button type="button" className="btn btn-primary btn-block" onClick={onNew}>
            <svg viewBox="0 0 20 20" aria-hidden="true" className="btn-icon">
              <path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            </svg>
            Neues Projekt
          </button>
          <button type="button" className="btn btn-ghost btn-block" onClick={onImport}>
            <svg viewBox="0 0 20 20" aria-hidden="true" className="btn-icon">
              <path d="M10 13V3m0 0L6.5 6.5M10 3l3.5 3.5M4 13v3h12v-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Importieren
          </button>
        </div>

        <div className="search">
          <SearchIcon />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Projekt suchen …"
            aria-label="Projekte durchsuchen"
          />
        </div>

        <nav className="project-list" aria-label="Projekte">
          {filtered.length === 0 && (
            <p className="empty-note">
              {projects.length === 0 ? 'Noch keine Projekte.' : 'Kein Projekt gefunden.'}
            </p>
          )}
          {filtered.map((project) => (
            <button
              key={project.id}
              type="button"
              className={`project-item ${project.id === selectedId ? 'is-active' : ''}`}
              onClick={() => onSelect(project.id)}
              title={project.name}
            >
              <span className="project-name">{project.name}</span>
              <span className="project-meta">
                {project.sheets} {project.sheets === 1 ? 'Plan' : 'Pläne'} · {project.views}{' '}
                {project.views === 1 ? 'Ansicht' : 'Ansichten'} · {relativeTime(project.modified)}
              </span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className={`health ${healthClass}`}>
            <span className="dot" aria-hidden="true" />
            <span>{health ? (healthy ? 'Server bereit' : 'Eingeschränkt') : 'Verbindung …'}</span>
          </div>
          <span className="version">v{info?.version || '–'}</span>
        </div>
      </aside>
    </>
  );
}