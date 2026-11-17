import { useEffect, useState } from 'react';
import * as api from '../api';
import { formatDuration } from '../format.js';
import { StatusBadge } from './JobsTab.jsx';

export default function Viewer({ job, title, onClose }) {
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const handleKey = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', handleKey);
    document.body.classList.add('modal-open');
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.classList.remove('modal-open');
    };
  }, [onClose]);

  const zoomBy = (delta) =>
    setZoom((value) => {
      const next = Math.min(4, Math.max(0.5, Number((value + delta).toFixed(2))));
      return next;
    });

  const running = job && (job.status === 'queued' || job.status === 'running');

  return (
    <div
      className="modal-backdrop viewer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="viewer" role="dialog" aria-modal="true" aria-label={title}>
        <header className="viewer-head">
          <div className="viewer-title">
            <span className="micro">Zeichnung</span>
            <h2>{title}</h2>
          </div>
          <div className="viewer-head-actions">
            {job?.artifact && (
              <a
                className="btn btn-sm"
                href={api.artifactUrl(job.id, false)}
                download
                title="Artefakt herunterladen"
              >
                Herunterladen
              </a>
            )}
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              aria-label="Viewer schließen"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true">
                <path
                  d="M5 5l10 10M15 5 5 15"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        </header>

        <div className="viewer-body">
          {!job && (
            <div className="viewer-state">
              <span className="spinner spinner-lg" />
              <p>Job wird geladen …</p>
            </div>
          )}

          {running && (
            <div className="viewer-state">
              <span className="spinner spinner-lg" />
              <p>
                {job.status === 'queued'
                  ? 'Wartet in der Warteschlange …'
                  : 'Zeichnung wird gerendert …'}
              </p>
            </div>
          )}

          {job?.status === 'error' && (
            <div className="card viewer-error">
              <div className="micro">Fehler</div>
              <h3>Die Zeichnung konnte nicht erstellt werden.</h3>
              <p>{job.error || 'Unbekannter Fehler'}</p>
              <a
                className="link-sm"
                href={api.jobReportUrl(job.id)}
                target="_blank"
                rel="noreferrer"
              >
                Vollständigen Fehlerbericht öffnen
              </a>
            </div>
          )}

          {job?.status === 'done' && job.artifact && (
            <div className="viewer-canvas">
              <img
                src={api.artifactUrl(job.id, true)}
                alt={`Zeichnung ${title}`}
                style={{ transform: `scale(${zoom})` }}
              />
            </div>
          )}

          {job?.status === 'done' && !job.artifact && (
            <pre className="result-text viewer-text">
              {job.result?.text || JSON.stringify(job.result ?? {}, null, 2)}
            </pre>
          )}
        </div>

        <footer className="viewer-foot">
          <div className="zoom">
            <button
              type="button"
              className="icon-btn icon-btn-sm"
              onClick={() => zoomBy(-0.25)}
              aria-label="Verkleinern"
              disabled={!job?.artifact}
            >
              −
            </button>
            <span className="zoom-value">{Math.round(zoom * 100)} %</span>
            <button
              type="button"
              className="icon-btn icon-btn-sm"
              onClick={() => zoomBy(0.25)}
              aria-label="Vergrößern"
              disabled={!job?.artifact}
            >
              +
            </button>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => setZoom(1)}
              disabled={!job?.artifact}
            >
              Einpassen
            </button>
          </div>

          <div className="viewer-meta">
            {job && (
              <>
                <StatusBadge status={job.status} />
                {job.duration_ms != null && (
                  <span className="muted">{formatDuration(job.duration_ms)}</span>
                )}
                {job.exit_code != null && (
                  <span className="muted">Exit {job.exit_code}</span>
                )}
              </>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}