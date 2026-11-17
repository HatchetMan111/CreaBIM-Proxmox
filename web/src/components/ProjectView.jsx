import { useEffect, useRef, useState } from 'react';
import * as api from '../api';
import { projectKindLabel } from '../format.js';
import OverviewTab from './OverviewTab.jsx';
import DrawingsTab from './DrawingsTab.jsx';
import ExportTab from './ExportTab.jsx';
import ChecksTab from './ChecksTab.jsx';
import JobsTab from './JobsTab.jsx';

const TABS = [
  { key: 'overview', label: 'Übersicht' },
  { key: 'drawings', label: 'Zeichnungen' },
  { key: 'export', label: 'Export' },
  { key: 'checks', label: 'Prüfung' },
  { key: 'jobs', label: 'Jobs' },
];

function EditableTitle({ value, onCommit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef(null);
  const cancelRef = useRef(false);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const start = () => {
    cancelRef.current = false;
    setDraft(value);
    setEditing(true);
  };

  const commit = () => {
    if (cancelRef.current) return;
    const trimmed = draft.trim();
    setEditing(false);
    if (trimmed && trimmed !== value) onCommit(trimmed);
  };

  return (
    <h1 className="project-title">
      {editing ? (
        <input
          ref={inputRef}
          className="title-input"
          value={draft}
          maxLength={120}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commit();
            }
            if (event.key === 'Escape') {
              event.preventDefault();
              cancelRef.current = true;
              setDraft(value);
              setEditing(false);
            }
          }}
          aria-label="Projektname"
        />
      ) : (
        <button
          type="button"
          className="title-btn"
          onClick={start}
          title="Projekt umbenennen"
        >
          <span className="title-text">{value}</span>
          <svg viewBox="0 0 20 20" aria-hidden="true" className="pencil">
            <path
              d="M13.5 4.5 15.5 6.5 7 15H5v-2l8.5-8.5Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}
    </h1>
  );
}

export default function ProjectView({
  project,
  structure,
  info,
  health,
  jobs,
  tab,
  onTab,
  onRename,
  onRequestRename,
  onRequestDelete,
  onRequestCreabim,
  onStartJob,
  onRender,
  onRefreshStructure,
  refreshing,
}) {
  const projectJobs = jobs.filter((job) => job.project_id === project.id);

  return (
    <div className="page">
      <header className="project-head">
        <div>
          <div className="micro">Projekt</div>
          <div className="project-title-row">
            <EditableTitle value={project.name} onCommit={onRename} />
            <span className="badge badge-kind">{projectKindLabel(project.kind)}</span>
          </div>
        </div>

        <div className="head-actions">
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={onRequestCreabim}
            title="Projektdatei für die CreaBIM-Desktop-App laden"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true" className="btn-icon">
              <path
                d="M4 16.5V9.5L10 4l6 5.5v7h-4.5v-4h-3v4H4Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            In CreaBIM öffnen
          </button>
          <a
            className="btn btn-sm"
            href={api.modelUrl(project.id)}
            download
            title="Modelldatei herunterladen"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true" className="btn-icon">
              <path
                d="M10 3v9m0 0 3.5-3.5M10 12 6.5 8.5M4 15.5h12"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Modell herunterladen
          </a>
          <button type="button" className="btn btn-sm" onClick={onRequestRename}>
            Umbenennen
          </button>
          <button type="button" className="btn btn-sm btn-danger-ghost" onClick={onRequestDelete}>
            Löschen
          </button>
        </div>
      </header>

      <nav className="tabs" aria-label="Projektbereiche">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`tab ${tab === item.key ? 'is-active' : ''}`}
            onClick={() => onTab(item.key)}
            aria-current={tab === item.key ? 'page' : undefined}
          >
            {item.label}
            {item.key === 'jobs' && projectJobs.length > 0 && (
              <span className="tab-count">{projectJobs.length}</span>
            )}
          </button>
        ))}
      </nav>

      {tab === 'overview' && (
        <OverviewTab
          project={project}
          structure={structure}
          jobs={projectJobs}
          info={info}
          health={health}
        />
      )}

      {tab === 'drawings' && (
        <DrawingsTab
          structure={structure}
          jobs={projectJobs}
          onRender={onRender}
          onRefresh={onRefreshStructure}
          refreshing={refreshing}
        />
      )}

      {tab === 'export' && (
        <ExportTab
          actions={info?.actions || []}
          jobs={projectJobs}
          project={project}
          onStartJob={onStartJob}
        />
      )}

      {tab === 'checks' && (
        <ChecksTab
          actions={info?.actions || []}
          jobs={projectJobs}
          project={project}
          onStartJob={onStartJob}
        />
      )}

      {tab === 'jobs' && (
        <JobsTab
          jobs={projectJobs}
          projects={[project]}
          title="Jobs dieses Projekts"
        />
      )}
    </div>
  );
}