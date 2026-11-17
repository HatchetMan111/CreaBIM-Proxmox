import { Fragment, useState } from 'react';
import * as api from '../api';
import { formatDuration, relativeTime } from '../format.js';

const STATUS_LABELS = {
  queued: 'Warteschlange',
  running: 'Läuft',
  done: 'Fertig',
  error: 'Fehler',
};

export function StatusBadge({ status }) {
  const key = STATUS_LABELS[status] ? status : 'queued';
  return <span className={`badge badge-status-${key}`}>{STATUS_LABELS[key]}</span>;
}

function ResultPreview({ job }) {
  const result = job.result;
  if (result == null) return <p className="muted small">Kein Ergebnis.</p>;
  if (typeof result === 'string') return <pre className="result-text">{result}</pre>;
  if (result.text) return <pre className="result-text">{result.text}</pre>;
  return <pre className="result-text">{JSON.stringify(result, null, 2)}</pre>;
}

export default function JobsTab({ jobs, projects, onOpenProject, title = 'Jobs' }) {
  const [openId, setOpenId] = useState(null);
  const [reports, setReports] = useState({});
  const [reportErrors, setReportErrors] = useState({});
  const [reportLoading, setReportLoading] = useState(null);

  const projectName = (job) => {
    const known = projects?.find((project) => project.id === job.project_id);
    return known?.name || job.project_name || job.project_id;
  };

  const toggle = async (job) => {
    if (openId === job.id) {
      setOpenId(null);
      return;
    }
    setOpenId(job.id);

    if (reports[job.id] !== undefined || reportErrors[job.id]) return;

    setReportLoading(job.id);
    try {
      const text = await api.fetchJobReport(job.id);
      setReports((prev) => ({ ...prev, [job.id]: text }));
    } catch (err) {
      setReportErrors((prev) => ({
        ...prev,
        [job.id]: err instanceof Error ? err.message : 'Unbekannter Fehler',
      }));
    } finally {
      setReportLoading(null);
    }
  };

  return (
    <section className="tab-body">
      <div className="section-head">
        <h2>{title}</h2>
        <span className="muted">{jobs.length} Jobs</span>
      </div>

      {jobs.length === 0 ? (
        <div className="card empty-note-block">
          Noch keine Jobs vorhanden. Zeichnungen und Exporte erscheinen hier.
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="data job-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Aktion</th>
                <th>Projekt</th>
                <th className="num">Dauer</th>
                <th className="num">Exit</th>
                <th className="num">Details</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const isOpen = openId === job.id;
                return (
                  <Fragment key={job.id}>
                    <tr
                      className={`job-row ${isOpen ? 'is-open' : ''}`}
                      onClick={() => toggle(job)}
                    >
                      <td>
                        <StatusBadge status={job.status} />
                      </td>
                      <td>
                        <span className="job-action">{job.label}</span>
                        <span className="job-sub">
                          {job.action} · {relativeTime(
                            new Date(job.created * 1000).toISOString(),
                          )}
                        </span>
                      </td>
                      <td>
                        {onOpenProject ? (
                          <button
                            type="button"
                            className="link-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              onOpenProject(job.project_id);
                            }}
                          >
                            {projectName(job)}
                          </button>
                        ) : (
                          projectName(job)
                        )}
                      </td>
                      <td className="num">{formatDuration(job.duration_ms)}</td>
                      <td className="num">{job.exit_code == null ? '–' : job.exit_code}</td>
                      <td className="num">
                        <span className="job-row-actions">
                          {job.artifact && (
                            <a
                              className="icon-link"
                              href={api.artifactUrl(job.id, false)}
                              download
                              title="Artefakt herunterladen"
                              aria-label="Artefakt herunterladen"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <svg viewBox="0 0 20 20" aria-hidden="true">
                                <path
                                  d="M10 3v9m0 0 3.5-3.5M10 12 6.5 8.5M4 15.5h12"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="1.6"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                              </svg>
                            </a>
                          )}
                          <button
                            type="button"
                            className="icon-btn icon-btn-sm"
                            aria-expanded={isOpen}
                            aria-label={isOpen ? 'Details zuklappen' : 'Details aufklappen'}
                          >
                            <svg
                              viewBox="0 0 20 20"
                              aria-hidden="true"
                              className={isOpen ? 'chevron is-open' : 'chevron'}
                            >
                              <path
                                d="m6 8 4 4 4-4"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.6"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          </button>
                        </span>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="job-detail-row">
                        <td colSpan={6}>
                          <div className="job-detail">
                            <div className="job-detail-head">
                              <span className="micro">
                                {job.status === 'error' ? 'Fehlerbericht' : 'Meldung'}
                              </span>
                              <span className="job-id">Job {job.id}</span>
                            </div>

                            {reportLoading === job.id && (
                              <p className="muted small">
                                <span className="spinner" /> Bericht wird geladen …
                              </p>
                            )}

                            {reportErrors[job.id] && (
                              <p className="form-error">{reportErrors[job.id]}</p>
                            )}

                            {reports[job.id] !== undefined && (
                              <pre className="result-text report-text">{reports[job.id]}</pre>
                            )}

                            {reports[job.id] === undefined &&
                              reportErrors[job.id] === undefined &&
                              reportLoading !== job.id && (
                                <>
                                  {job.error && (
                                    <p className="job-error-text">
                                      {job.error}{' '}
                                      <a
                                        href={api.jobReportUrl(job.id)}
                                        target="_blank"
                                        rel="noreferrer"
                                      >
                                        Bericht öffnen
                                      </a>
                                    </p>
                                  )}
                                  {job.result != null && (
                                    <div className="result-box">
                                      <ResultPreview job={job} />
                                    </div>
                                  )}
                                  <a
                                    className="link-sm"
                                    href={api.jobReportUrl(job.id)}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    Vollständigen Bericht öffnen
                                  </a>
                                </>
                              )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}