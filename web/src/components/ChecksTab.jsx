import * as api from '../api';
import { isRunning } from '../format.js';

function ResultWait({ job }) {
  if (!isRunning(job)) return null;
  return (
    <div className="result-wait">
      <span className="spinner" />
      <span>{job.status === 'queued' ? 'Wartet in der Warteschlange …' : 'Wird ausgeführt …'}</span>
    </div>
  );
}

function ErrorBox({ job }) {
  if (job?.status !== 'error') return null;
  return (
    <div className="result-box result-error" role="alert">
      <div className="result-head">Fehler</div>
      <p className="result-message">{job.error || 'Unbekannter Fehler'}</p>
      <a
        className="link-sm"
        href={api.jobReportUrl(job.id)}
        target="_blank"
        rel="noreferrer"
      >
        Vollständigen Bericht öffnen
      </a>
    </div>
  );
}

function CheckResult({ job }) {
  if (!job || job.status !== 'done') return null;
  const ok = job.result?.ok === true;
  return (
    <div className={`result-box ${ok ? 'result-ok' : 'result-warn'}`}>
      <div className="result-head">
        {ok ? 'Keine Fehler gefunden' : 'Prüfung mit Fehlern'}
      </div>
      <pre className="result-text">{job.result?.text || '(keine Ausgabe)'}</pre>
    </div>
  );
}

function ClashResult({ job }) {
  if (!job || job.status !== 'done') return null;
  const text = String(job.result?.text || '').trim();
  return (
    <div className={`result-box ${text ? 'result-warn' : 'result-ok'}`}>
      <div className="result-head">
        {text ? 'Konflikte gefunden' : 'Keine Konflikte'}
      </div>
      <pre className="result-text">{text || '(keine Ausgabe)'}</pre>
    </div>
  );
}

function StatsResult({ job }) {
  if (!job || job.status !== 'done') return null;
  const entries = Object.entries(job.result || {});
  return (
    <div className="result-box">
      <div className="result-head">{entries.length} IFC-Klassen</div>
      {entries.length === 0 ? (
        <pre className="result-text">(keine Elemente)</pre>
      ) : (
        <table className="data compact-table">
          <tbody>
            {entries
              .sort((a, b) => b[1] - a[1])
              .map(([name, count]) => (
                <tr key={name}>
                  <td className="stat-name">{name}</td>
                  <td className="num stat-value">{count}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function ChecksTab({ actions, jobs, project, onStartJob }) {
  const byKey = Object.fromEntries(actions.map((action) => [action.key, action]));

  const latest = (key) =>
    jobs.find((job) => job.project_id === project.id && job.action === key) || null;

  const cards = [
    {
      key: 'check',
      action: byKey.check,
      title: 'Modell prüfen',
      description:
        'Prüft Türen, Türanschläge und Wandanschlüsse auf Fehler im Modell.',
      result: <CheckResult job={latest('check')} />,
    },
    {
      key: 'label-clashes',
      action: byKey['label-clashes'],
      title: 'Beschriftungs-Konflikte',
      description:
        'Findet Labels, Marken und Notizen, die sich in Grundrissen überlappen.',
      result: <ClashResult job={latest('label-clashes')} />,
    },
    {
      key: 'stats',
      action: byKey.stats,
      title: 'Element-Statistik',
      description: 'Zählt alle Elemente des Modells nach IFC-Klasse.',
      result: <StatsResult job={latest('stats')} />,
    },
  ];

  return (
    <div className="tab-body">
      <div className="section-head">
        <h2>Prüfung &amp; Auswertung</h2>
        <span className="muted">{cards.length} Prüfungen</span>
      </div>

      <div className="check-grid">
        {cards.map((card) => {
          const job = latest(card.key);
          const running = isRunning(job);
          return (
            <section key={card.key} className="card check-card">
              <h3>{card.title}</h3>
              <p className="export-desc">
                {card.action?.description || card.description}
              </p>

              <div className="check-actions">
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => onStartJob(card.key)}
                  disabled={running}
                >
                  {running ? (
                    <>
                      <span className="spinner" /> Läuft …
                    </>
                  ) : (
                    card.title
                  )}
                </button>
                {job?.status === 'done' && (
                  <span className="muted small">
                    {new Date(job.finished * 1000).toLocaleTimeString('de-DE', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                )}
              </div>

              <ResultWait job={job} />
              <ErrorBox job={job} />
              {card.result}
            </section>
          );
        })}
      </div>
    </div>
  );
}