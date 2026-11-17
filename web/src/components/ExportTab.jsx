import { useState } from 'react';
import * as api from '../api';
import { isRunning } from '../format.js';
import { StatusBadge } from './JobsTab.jsx';

function defaultParams(action) {
  const values = {};
  for (const param of action.params || []) {
    values[param.name] = param.default ?? '';
  }
  return values;
}

function ExportCard({ action, job, onStart }) {
  const [params, setParams] = useState(() => defaultParams(action));
  const running = isRunning(job);

  const update = (name, value) =>
    setParams((prev) => ({ ...prev, [name]: value }));

  return (
    <div className="card export-card">
      <div className="export-card-top">
        <h3>{action.label}</h3>
        {job && <StatusBadge status={job.status} />}
      </div>

      <p className="export-desc">{action.description}</p>

      {action.params?.length > 0 && (
        <div className="export-params">
          {action.params.map((param) => (
            <label key={param.name} className="field field-inline">
              <span>{param.label}</span>
              {param.kind === 'choice' && param.choices?.length > 0 ? (
                <select
                  className="input"
                  value={params[param.name] ?? ''}
                  onChange={(event) => update(param.name, event.target.value)}
                  disabled={running}
                >
                  {param.choices.map((choice) => (
                    <option key={choice} value={choice}>
                      {choice}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="input"
                  value={params[param.name] ?? ''}
                  onChange={(event) => update(param.name, event.target.value)}
                  disabled={running}
                />
              )}
            </label>
          ))}
        </div>
      )}

      <div className="export-foot">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => onStart(action.key, params)}
          disabled={running}
        >
          {running ? (
            <>
              <span className="spinner" /> Läuft …
            </>
          ) : (
            'Exportieren'
          )}
        </button>

        {job?.status === 'done' && job.artifact && (
          <a
            className="btn btn-sm"
            href={api.artifactUrl(job.id, false)}
            download
            title={`${action.label} herunterladen`}
          >
            Herunterladen
          </a>
        )}

        {job?.status === 'done' && !job.artifact && (
          <span className="muted small">Fertig</span>
        )}

        {job?.status === 'error' && (
          <a
            className="link-sm"
            href={api.jobReportUrl(job.id)}
            target="_blank"
            rel="noreferrer"
          >
            Fehlerbericht
          </a>
        )}
      </div>
    </div>
  );
}

export default function ExportTab({ actions, jobs, project, onStartJob }) {
  const exportActions = actions.filter((action) => {
    const group = String(action.group || '').toLowerCase();
    return group === 'export';
  });

  return (
    <div className="tab-body">
      <div className="section-head">
        <h2>Export</h2>
        <span className="muted">{exportActions.length} Formate</span>
      </div>

      {exportActions.length === 0 ? (
        <p className="muted">Keine Exportformate verfügbar.</p>
      ) : (
        <div className="export-grid">
          {exportActions.map((action) => {
            const job =
              jobs.find(
                (item) => item.project_id === project.id && item.action === action.key,
              ) || null;
            return (
              <ExportCard
                key={action.key}
                action={action}
                job={job}
                onStart={onStartJob}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}