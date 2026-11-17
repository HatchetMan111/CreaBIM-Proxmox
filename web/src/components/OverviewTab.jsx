import { useMemo, useState } from 'react';
import { StatusBadge } from './JobsTab.jsx';
import { formatDuration, relativeTime } from '../format.js';

function Tile({ label, value, hint }) {
  return (
    <div className="card tile">
      <div className="tile-value">{value}</div>
      <div className="tile-label">{label}</div>
      {hint && <div className="tile-hint">{hint}</div>}
    </div>
  );
}

export default function OverviewTab({ project, structure, jobs, info, health }) {
  const [sortDesc, setSortDesc] = useState(true);

  const stats = structure?.stats || {};
  const entries = useMemo(() => Object.entries(stats), [stats]);
  const total = useMemo(
    () => entries.reduce((sum, [, count]) => sum + count, 0),
    [entries],
  );

  const sorted = useMemo(() => {
    const list = [...entries];
    list.sort((a, b) => (sortDesc ? b[1] - a[1] : a[1] - b[1]));
    return list;
  }, [entries, sortDesc]);

  const recentJobs = jobs.slice(0, 6);
  const cliPath = health?.cli || info?.cli || 'creabim-cli';

  return (
    <div className="tab-body">
      <div className="tiles">
        <Tile label="Geschosse" value={structure?.levels?.length || 0} />
        <Tile label="Ansichten" value={structure?.views?.length || 0} />
        <Tile label="Pläne" value={structure?.sheets?.length || 0} />
        <Tile label="Elemente" value={total} hint={`${entries.length} IFC-Klassen`} />
      </div>

      <div className="overview-grid">
        <section className="card stats-card">
          <div className="section-head section-head-tight">
            <h2>Element-Statistik</h2>
            <span className="muted">{total} Elemente</span>
          </div>

          {sorted.length === 0 ? (
            <p className="muted">Keine Statistik verfügbar.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>IFC-Klasse</th>
                    <th className="num">
                      <button
                        type="button"
                        className="sort-button"
                        onClick={() => setSortDesc((value) => !value)}
                        title="Sortierung umschalten"
                      >
                        Anzahl
                        <span aria-hidden="true">{sortDesc ? '↓' : '↑'}</span>
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(([name, count]) => (
                    <tr key={name}>
                      <td className="stat-name">{name}</td>
                      <td className="num stat-value">{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card activity-card">
          <div className="section-head section-head-tight">
            <h2>Letzte Aktionen</h2>
            <span className="muted">{jobs.length}</span>
          </div>

          {recentJobs.length === 0 ? (
            <p className="muted">Noch keine Jobs für dieses Projekt.</p>
          ) : (
            <ul className="activity-list">
              {recentJobs.map((job) => (
                <li key={job.id} className="activity-row">
                  <div className="activity-main">
                    <span className="activity-label">{job.label}</span>
                    <span className="activity-meta">
                      {relativeTime(new Date(job.created * 1000).toISOString())} ·{' '}
                      {job.status === 'done'
                        ? formatDuration(job.duration_ms)
                        : job.status === 'error'
                          ? `Exit ${job.exit_code ?? '–'}`
                          : 'in Arbeit'}
                    </span>
                  </div>
                  <StatusBadge status={job.status} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="overview-foot">
        <section className="card note-card">
          <span className="micro">Engine</span>
          <h3>creabim-cli</h3>
          <p className="mono-path">{cliPath}</p>
          <p className="muted small">
            Server v{info?.version || health?.version || '–'} · Datenverzeichnis{' '}
            <span className="mono">{info?.data_dir || '–'}</span>
          </p>
        </section>

        <section className="card note-card">
          <span className="micro">Modell</span>
          <h3>{project.model || '–'}</h3>
          <p className="muted small">
            {project.kind ? `${project.kind} · ` : ''}
            {structure?.levels?.length || 0} Geschosse ·{' '}
            {structure?.views?.length || 0} Ansichten ·{' '}
            {structure?.sheets?.length || 0} Pläne
          </p>
          {structure?.generated && (
            <p className="muted small">
              Struktur gelesen: {relativeTime(structure.generated)}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}