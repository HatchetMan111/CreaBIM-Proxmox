import { viewKindLabel } from '../format.js';

function ParamsMatch({ job, action, paramName, value }) {
  return (
    job &&
    job.action === action &&
    job.params &&
    String(job.params[paramName] ?? '') === String(value)
  );
}

export default function DrawingsTab({ structure, jobs, onRender, onRefresh, refreshing }) {
  const sheets = structure?.sheets || [];
  const views = structure?.views || [];

  return (
    <div className="tab-body">
      <div className="section-head">
        <h2>Zeichnungen</h2>
        <button
          type="button"
          className="btn btn-sm"
          onClick={onRefresh}
          disabled={refreshing}
        >
          {refreshing ? (
            <>
              <span className="spinner" /> Aktualisiert …
            </>
          ) : (
            'Aktualisieren'
          )}
        </button>
      </div>

      <div className="drawings-grid">
        <section>
          <div className="subhead">
            <h3>Pläne (Sheets)</h3>
            <span className="muted">{sheets.length}</span>
          </div>

          {sheets.length === 0 ? (
            <p className="muted">Dieses Modell enthält keine Pläne.</p>
          ) : (
            <div className="sheet-grid">
              {sheets.map((sheet) => {
                const running = jobs.find((job) =>
                  ParamsMatch(job, 'sheet', 'number', sheet.number) &&
                  (job.status === 'queued' || job.status === 'running'),
                );
                return (
                  <button
                    key={sheet.number}
                    type="button"
                    className={`card sheet-card ${running ? 'is-running' : ''}`}
                    onClick={() =>
                      onRender('sheet', { number: sheet.number }, `Plan ${sheet.number}`)
                    }
                    title={sheet.name || `Plan ${sheet.number} zeichnen`}
                  >
                    <span className="sheet-top">
                      <span className="sheet-num">{sheet.number}</span>
                      <span className="badge badge-kind">{sheet.size || '–'}</span>
                    </span>
                    <span className="sheet-name">{sheet.name || 'Ohne Titel'}</span>
                    <span className="sheet-hint">
                      {running ? (
                        <>
                          <span className="spinner" /> Wird gezeichnet …
                        </>
                      ) : (
                        'Als SVG zeichnen'
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <section>
          <div className="subhead">
            <h3>Ansichten</h3>
            <span className="muted">{views.length}</span>
          </div>

          {views.length === 0 ? (
            <p className="muted">Dieses Modell enthält keine Ansichten.</p>
          ) : (
            <div className="card view-list">
              {views.map((view) => {
                const running = jobs.find(
                  (job) =>
                    ParamsMatch(job, 'view', 'name', view.name) &&
                    (job.status === 'queued' || job.status === 'running'),
                );
                return (
                  <button
                    key={`${view.name}-${view.kind}`}
                    type="button"
                    className={`view-row ${running ? 'is-running' : ''}`}
                    onClick={() => onRender('view', { name: view.name }, view.name)}
                    title={view.name}
                  >
                    <span className="view-main">
                      <span className="view-name">{view.name}</span>
                      <span className="view-meta">
                        {viewKindLabel(view.kind)}
                        {view.level ? ` · ${view.level}` : ''}
                      </span>
                    </span>
                    <span className="view-side">
                      {running ? (
                        <span className="spinner" />
                      ) : (
                        <span className="view-scale">{view.scale || '–'}</span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <p className="hint-line">
        Ein Klick rendert die Zeichnung als Job und öffnet den Viewer. Pläne
        enthalten den Titelblock, Ansichten werden direkt aus dem Modell gezeichnet.
      </p>
    </div>
  );
}