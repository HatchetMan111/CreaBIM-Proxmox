// Schlanker fetch-Wrapper um die CreaBIM-Server-API.
// Alle Antworten sind entweder JSON oder Text – Fehler werden zu ApiError
// normalisiert, damit die UI überall gleich reagieren kann.

const BASE = '/api';

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function detailToText(detail) {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          return item.msg || item.message || JSON.stringify(item);
        }
        return String(item);
      })
      .join('; ');
  }
  if (typeof detail === 'object') {
    return detail.message || detail.error || JSON.stringify(detail);
  }
  return String(detail);
}

async function readError(res) {
  let detail = null;
  try {
    const data = await res.json();
    detail = data.detail ?? data.error ?? data.message ?? null;
  } catch {
    try {
      const text = await res.text();
      if (text) detail = text;
    } catch {
      detail = null;
    }
  }
  const message = detailToText(detail) || `HTTP ${res.status}`;
  return new ApiError(message, res.status, detail);
}

async function request(path, { method = 'GET', json, form } = {}) {
  const init = { method, headers: {} };

  if (json !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }

  let res;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(
      'Der Server ist nicht erreichbar. Läuft die CreaBIM-Server-Instanz?',
      0,
    );
  }

  if (!res.ok) throw await readError(res);
  if (res.status === 204) return null;

  const type = res.headers.get('content-type') || '';
  if (type.includes('application/json')) return res.json();
  return res.text();
}

const id = (value) => encodeURIComponent(value);

export const getHealth = () => request('/health');
export const getInfo = () => request('/info');

export const listProjects = async () => {
  const data = await request('/projects');
  return data.projects || [];
};

export const createProject = async (sample, name) => {
  const data = await request('/projects', {
    method: 'POST',
    json: { sample, name: name || undefined },
  });
  return data.project;
};

export const importProject = async (file, name) => {
  const form = new FormData();
  form.append('file', file);
  if (name) form.append('name', name);
  const data = await request('/projects/import', { method: 'POST', form });
  return data.project;
};

export const getProject = async (pid) => {
  const data = await request(`/projects/${id(pid)}`);
  return { project: data.project, structure: data.structure };
};

export const renameProject = async (pid, name) => {
  const data = await request(`/projects/${id(pid)}`, {
    method: 'PATCH',
    json: { name },
  });
  return data.project;
};

export const deleteProject = (pid) =>
  request(`/projects/${id(pid)}`, { method: 'DELETE' });

export const getStructure = async (pid, refresh = false) => {
  const data = await request(`/projects/${id(pid)}/structure?refresh=${refresh ? 'true' : 'false'}`);
  return data.structure;
};

export const startJob = async (pid, action, params = {}) => {
  const data = await request(`/projects/${id(pid)}/jobs`, {
    method: 'POST',
    json: { action, params },
  });
  return data.job;
};

export const listJobs = async (limit = 50) => {
  const data = await request(`/jobs?limit=${limit}`);
  return data.jobs || [];
};

export const getJob = async (jid) => {
  const data = await request(`/jobs/${id(jid)}`);
  return data.job;
};

export const fetchJobReport = (jid) =>
  request(`/jobs/${id(jid)}/report`);

export const jobReportUrl = (jid) => `${BASE}/jobs/${id(jid)}/report`;

export const artifactUrl = (jid, inline = false) =>
  `${BASE}/jobs/${id(jid)}/artifact?inline=${inline ? '1' : '0'}`;

export const modelUrl = (pid) => `${BASE}/projects/${id(pid)}/model`;

export function errorMessage(err) {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return String(err);
}