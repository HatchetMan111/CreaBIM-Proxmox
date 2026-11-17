import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from './api';
import Sidebar from './components/Sidebar.jsx';
import Dashboard from './components/Dashboard.jsx';
import ProjectView from './components/ProjectView.jsx';
import Viewer from './components/Viewer.jsx';
import Toasts from './components/Toasts.jsx';
import useJobs from './useJobs.js';
import {
  DeleteDialog,
  ImportDialog,
  NewProjectDialog,
  RenameDialog,
} from './components/ProjectDialogs.jsx';

const JOB_LIMIT = 50;

export default function App() {
  const [health, setHealth] = useState(null);
  const [info, setInfo] = useState(null);
  const [projects, setProjects] = useState([]);
  const { jobs, setJobs } = useJobs(JOB_LIMIT);
  const [current, setCurrent] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [tab, setTab] = useState('overview');
  const [toasts, setToasts] = useState([]);
  const [dialog, setDialog] = useState(null);
  const [dialogError, setDialogError] = useState('');
  const [dialogBusy, setDialogBusy] = useState(false);
  const [viewer, setViewer] = useState(null);
  const [switching, setSwitching] = useState(false);
  const [structureBusy, setStructureBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [bootError, setBootError] = useState(null);
  const [bootNonce, setBootNonce] = useState(0);
  const selectToken = useRef(0);

  const pushToast = useCallback((kind, message) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev, { id, kind, message }].slice(-4));
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  // ── Initiales Laden ────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    setBootError(null);

    (async () => {
      const [healthResult, infoResult, projectsResult, jobsResult] =
        await Promise.allSettled([
          api.getHealth(),
          api.getInfo(),
          api.listProjects(),
          api.listJobs(JOB_LIMIT),
        ]);

      if (!alive) return;

      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      if (infoResult.status === 'fulfilled') setInfo(infoResult.value);
      if (projectsResult.status === 'fulfilled') setProjects(projectsResult.value);
      if (jobsResult.status === 'fulfilled') setJobs(jobsResult.value);

      const failed = [healthResult, infoResult, projectsResult, jobsResult].find(
        (result) => result.status === 'rejected',
      );
      if (failed) setBootError(api.errorMessage(failed.reason));
    })();

    return () => {
      alive = false;
    };
  }, [bootNonce]);

  // Health alle 30 s – aktualisiert Dot und Version in der Sidebar.
  useEffect(() => {
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const next = await api.getHealth();
        if (alive) setHealth(next);
      } catch {
        /* Health-Polling darf die Oberfläche nicht stören. */
      }
    }, 30000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const refreshProjects = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      pushToast('error', api.errorMessage(err));
    }
  }, [pushToast]);

  // ── Projekt wechseln ───────────────────────────────────────────────────
  const selectProject = useCallback(
    async (pid) => {
      const token = ++selectToken.current;
      setSidebarOpen(false);
      setTab('overview');
      setSelectedId(pid || null);

      if (!pid) {
        setCurrent(null);
        setSwitching(false);
        return;
      }

      setCurrent(null);
      setSwitching(true);
      try {
        const data = await api.getProject(pid);
        if (token !== selectToken.current) return;
        setCurrent(data);
      } catch (err) {
        if (token === selectToken.current) {
          pushToast('error', api.errorMessage(err));
          setSelectedId(null);
        }
      } finally {
        if (token === selectToken.current) setSwitching(false);
      }
    },
    [pushToast],
  );

  const refreshStructure = useCallback(async () => {
    if (!current) return;
    setStructureBusy(true);
    try {
      const structure = await api.getStructure(current.project.id, true);
      setCurrent((prev) => (prev ? { ...prev, structure } : prev));
      pushToast('success', 'Struktur neu eingelesen.');
    } catch (err) {
      pushToast('error', api.errorMessage(err));
    } finally {
      setStructureBusy(false);
    }
  }, [current, pushToast]);

  // ── Jobs starten ───────────────────────────────────────────────────────
  const startJob = useCallback(
    async (actionKey, params = {}) => {
      if (!current) return null;
      try {
        const job = await api.startJob(current.project.id, actionKey, params);
        setJobs((prev) => [job, ...prev.filter((item) => item.id !== job.id)]);
        return job;
      } catch (err) {
        pushToast('error', api.errorMessage(err));
        return null;
      }
    },
    [current, pushToast],
  );

  const renderDrawing = useCallback(
    async (actionKey, params, title) => {
      const job = await startJob(actionKey, params);
      if (job) setViewer({ jobId: job.id, title });
    },
    [startJob],
  );

  // ── Polling, solange Jobs laufen ───────────────────────────────────────
  // (useJobs übernimmt das zentrale Polling im 1200-ms-Takt.)

  // ── Dialoge ────────────────────────────────────────────────────────────
  const openDialog = useCallback((type) => {
    setSidebarOpen(false);
    setDialogError('');
    setDialogBusy(false);
    setDialog({ type });
  }, []);

  const closeDialog = useCallback(() => {
    setDialog(null);
    setDialogError('');
    setDialogBusy(false);
  }, []);

  const handleCreate = useCallback(
    async ({ sample, name }) => {
      setDialogBusy(true);
      setDialogError('');
      try {
        const project = await api.createProject(sample, name);
        await refreshProjects();
        setDialog(null);
        pushToast('success', `Projekt „${project.name}“ wurde angelegt.`);
        await selectProject(project.id);
      } catch (err) {
        const message = api.errorMessage(err);
        setDialogError(message);
        pushToast('error', message);
      } finally {
        setDialogBusy(false);
      }
    },
    [pushToast, refreshProjects, selectProject],
  );

  const handleImport = useCallback(
    async ({ file, name }) => {
      setDialogBusy(true);
      setDialogError('');
      try {
        const project = await api.importProject(file, name);
        await refreshProjects();
        setDialog(null);
        pushToast('success', `Projekt „${project.name}“ wurde importiert.`);
        await selectProject(project.id);
      } catch (err) {
        const message = api.errorMessage(err);
        setDialogError(message);
        pushToast('error', message);
      } finally {
        setDialogBusy(false);
      }
    },
    [pushToast, refreshProjects, selectProject],
  );

  const handleRename = useCallback(
    async (name) => {
      if (!current) return;
      try {
        const project = await api.renameProject(current.project.id, name);
        setCurrent((prev) => (prev ? { ...prev, project } : prev));
        setProjects((prev) =>
          prev.map((item) =>
            item.id === project.id ? { ...item, name: project.name } : item,
          ),
        );
        setDialog(null);
        pushToast('success', 'Projekt umbenannt.');
      } catch (err) {
        const message = api.errorMessage(err);
        setDialogError(message);
        pushToast('error', message);
      }
    },
    [current, pushToast],
  );

  const handleDelete = useCallback(async () => {
    if (!current) return;
    setDialogBusy(true);
    setDialogError('');
    try {
      const pid = current.project.id;
      await api.deleteProject(pid);
      setProjects((prev) => prev.filter((item) => item.id !== pid));
      setJobs((prev) => prev.filter((job) => job.project_id !== pid));
      setCurrent(null);
      setSelectedId(null);
      setDialog(null);
      pushToast('success', 'Projekt gelöscht.');
    } catch (err) {
      const message = api.errorMessage(err);
      setDialogError(message);
      pushToast('error', message);
    } finally {
      setDialogBusy(false);
    }
  }, [current, pushToast]);

  // ── Viewer ─────────────────────────────────────────────────────────────
  const viewerJob = useMemo(
    () => (viewer ? jobs.find((job) => job.id === viewer.jobId) || null : null),
    [jobs, viewer],
  );

  useEffect(() => {
    if (!viewer) return undefined;
    if (jobs.some((job) => job.id === viewer.jobId)) return undefined;

    let alive = true;
    api
      .getJob(viewer.jobId)
      .then((job) => {
        if (alive) {
          setJobs((prev) => [job, ...prev.filter((item) => item.id !== job.id)]);
        }
      })
      .catch(() => {
        /* Wenn der Job nicht lesbar ist, zeigt der Viewer den Ladezustand. */
      });

    return () => {
      alive = false;
    };
  }, [viewer, jobs]);

  const closeViewer = useCallback(() => setViewer(null), []);

  const degraded = health && health.status !== 'ok';

  return (
    <div className="app">
      <Sidebar
        projects={projects}
        selectedId={selectedId}
        onSelect={selectProject}
        onNew={() => openDialog('new')}
        onImport={() => openDialog('import')}
        health={health}
        info={info}
        open={sidebarOpen}
        onToggle={() => setSidebarOpen((value) => !value)}
      />

      <div className="main">
        <div className="mobile-bar">
          <button
            type="button"
            className="icon-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label="Navigation öffnen"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M4 6h12M4 10h12M4 14h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <span className="brand-mini">CreaBIM</span>
        </div>

        {switching && <div className="top-progress" aria-hidden="true" />}

        <main className="content">
          {bootError && (
            <div className="banner banner-warn" role="alert">
              <div>
                <strong>Server meldet einen Fehler.</strong>{' '}
                <span>{bootError}</span>
              </div>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setBootNonce((value) => value + 1)}
              >
                Erneut versuchen
              </button>
            </div>
          )}

          {degraded && (
            <div className="banner banner-warn" role="status">
              <div>
                <strong>Server eingeschränkt.</strong>{' '}
                <span>
                  Die CLI ist nicht verfügbar – Projekte und Jobs können fehlschlagen.
                  {(health.errors || []).map((message) => ` ${message}`).join('')}
                </span>
              </div>
            </div>
          )}

          {!health && !bootError && (
            <div className="boot-state">
              <span className="spinner spinner-lg" />
              <p>Server wird geladen …</p>
            </div>
          )}

          {health && !selectedId && (
            <Dashboard
              projects={projects}
              jobs={jobs}
              info={info}
              onOpenProject={selectProject}
              onNew={() => openDialog('new')}
              onImport={() => openDialog('import')}
            />
          )}

          {health && selectedId && current && (
            <ProjectView
              project={current.project}
              structure={current.structure}
              info={info}
              health={health}
              jobs={jobs}
              tab={tab}
              onTab={setTab}
              onRename={handleRename}
              onRequestRename={() => openDialog('rename')}
              onRequestDelete={() => openDialog('delete')}
              onStartJob={startJob}
              onRender={renderDrawing}
              onRefreshStructure={refreshStructure}
              refreshing={structureBusy}
            />
          )}

          {health && selectedId && !current && switching && (
            <div className="boot-state">
              <span className="spinner spinner-lg" />
              <p>Projekt wird geladen …</p>
            </div>
          )}
        </main>
      </div>

      {dialog?.type === 'new' && (
        <NewProjectDialog
          info={info}
          busy={dialogBusy}
          error={dialogError}
          onClose={closeDialog}
          onCreate={handleCreate}
        />
      )}

      {dialog?.type === 'import' && (
        <ImportDialog
          busy={dialogBusy}
          error={dialogError}
          onClose={closeDialog}
          onImport={handleImport}
        />
      )}

      {dialog?.type === 'rename' && current && (
        <RenameDialog
          projectName={current.project.name}
          busy={dialogBusy}
          error={dialogError}
          onClose={closeDialog}
          onRename={handleRename}
        />
      )}

      {dialog?.type === 'delete' && current && (
        <DeleteDialog
          projectName={current.project.name}
          busy={dialogBusy}
          error={dialogError}
          onClose={closeDialog}
          onDelete={handleDelete}
        />
      )}

      {viewer && (
        <Viewer job={viewerJob} title={viewer.title} onClose={closeViewer} />
      )}

      <Toasts toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}