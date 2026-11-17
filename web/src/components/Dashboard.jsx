import {
  formatBytes,
  formatDuration,
  projectKindLabel,
  relativeTime,
} from '../format.js';
import { StatusBadge } from './JobsTab.jsx';

function ProjectCard({ project, onOpen }) {
  return (
    <article className="card project-card">
      <div className="project-card-top">
        <h3>{project.name}</h3>
        <span className="badge badge-kind">{projectKindLabel(project.kind)}</span>
      </div>
      <div className="project-card-meta">
        <span>
          {project.sheets} {project.sheets === 1 ? 'Plan' : 'Pläne'}
        </span>
        <span>
          {project.views} {project.views === 1 ? 'Ansicht' : 'Ansichten'}
        </span>
        {project.size > 0 && <span>{formatBytes(project.size)}</span>}
      </div>
      <div className="project-card-foot">
        <span>{relativeTime(project.modified)}</span>
        <button type="button" className="link-button" onClick={() => onOpen(project.id)}>
          Öffnen →
        </button>
      </div>
    </article>
  );
}

function EngineCard({ info }) {
  const cliPath = info?.cli || 'creabim-cli';
  return (
    <section className="card engine-card">
      <div className="engine-intro">
        <span className="micro">Plan- und Export-Engine</span>
        <h2>Vom BIM-Modell zur geprüften Zeichnung.</h2>
        <p>
          CreaBIM Server bündelt die headless <span className="mono">creabim-cli</span>{' '}
          um Plan-, Schnitt- und Exportaufgaben. Jedes Modell bleibt lokal, jeder
          Lauf ist ein nachvollziehbarer Job mit Bericht und Artefakt.
        </p>
      </div>
      <div className="engine-grid">
        <div className="engine-item">
          <span className="engine-num">01</span>
          <h3>Zeichnen</h3>
          <p>Grundrisse, Schnitte und Pläne als Vektor-SVG – inklusive Titelblock.</p>
        </div>
        <div className="engine-item">
          <span className="engine-num">02</span>
          <h3>Prüfen</h3>
          <p>Modell- und Beschriftungsprüfung mit vollständiger Fehlerkette.</p>
        </div>
        <div className="engine-item">
          <span className="engine-num">03</span>
          <h3>Exportieren</h3>
          <p>PDF, Excel, IFC4, IFCX, glTF und FreeCAD aus derselben Modellquelle.</p>
        </div>
      </div>
      <p className="engine-path mono">{cliPath}</p>
    </section>
  );
}

function JobsPreview({ jobs, projects, onOpenProject }) {
  return (
    <section>
      <div className="section-head">
        <h2>Letzte Jobs</h2>
        <span className="muted">{jobs.length}</span>
      </div>
      {jobs.length === 0 ? (
        <div className="card empty-note-block">
          Noch keine Jobs. Sobald eine Zeichnung oder ein Export läuft, erscheint er hier.
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Status</th>
                <th>Aktion</th>
                <th>Projekt</th>
                <th className="num">Dauer</th>
                <th className="num">Exit</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const project = projects.find((item) => item.id === job.project_id);
                return (
                  <tr key={job.id}>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td>
                      <span className="job-action">{job.label}</span>
                      <span className="job-sub">
                        {relativeTime(new Date(job.created * 1000).toISOString())}
                      </span>
                    </td>
                    <td>
                      {project ? (
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => onOpenProject(project.id)}
                        >
                          {project.name}
                        </button>
                      ) : (
                        job.project_name
                      )}
                    </td>
                    <td className="num">{formatDuration(job.duration_ms)}</td>
                    <td className="num">{job.exit_code == null ? '–' : job.exit_code}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function Dashboard({
  projects,
  jobs,
  info,
  onOpenProject,
  onNew,
  onImport,
}) {
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="micro">CreaBIM Server</div>
          <h1>Übersicht</h1>
          <p className="lede">
            Willkommen im Zeichenbrett. Projekte verwalten, Zeichnungen rendern und
            Modelle prüfen – alles in einer ruhigen Oberfläche um die CreaBIM-CLI.
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn btn-primary" onClick={onNew}>
            Neues Projekt
          </button>
          <button type="button" className="btn" onClick={onImport}>
            Importieren
          </button>
        </div>
      </header>

      <section>
        <div className="section-head">
          <h2>Projekte</h2>
          <span className="muted">{projects.length}</span>
        </div>

        {projects.length === 0 ? (
          <div className="card empty-note-block empty-projects">
            <h3>Noch keine Projekte</h3>
            <p>
              Ein Beispielmodell anlegen oder eine eigene Datei importieren – danach
              stehen Zeichnungen, Prüfungen und Exporte bereit.
            </p>
            <div className="empty-actions">
              <button type="button" className="btn btn-primary btn-sm" onClick={onNew}>
                Beispielprojekt anlegen
              </button>
              <button type="button" className="btn btn-sm" onClick={onImport}>
                Modell importieren
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-projects">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} onOpen={onOpenProject} />
            ))}
          </div>
        )}
      </section>

      <EngineCard info={info} />

      <JobsPreview jobs={jobs.slice(0, 8)} projects={projects} onOpenProject={onOpenProject} />
    </div>
  );
}