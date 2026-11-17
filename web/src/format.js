// Kleine Helfer für Datums-, Zahlen- und Textformatierung (deutsch).

const VIEW_KIND_LABELS = {
  plan: 'Grundriss',
  section: 'Schnitt',
  elevation: 'Ansicht',
  '3d': '3D',
  axo: 'Axonometrie',
  model: 'Modell',
};

const PROJECT_KIND_LABELS = {
  creabim: 'CreaBIM',
  'creabim-json': 'CreaBIM JSON',
  ifc: 'IFC',
  ifcx: 'IFCX',
  spec: 'Spezifikation',
  model: 'Modell',
};

export const viewKindLabel = (kind) =>
  VIEW_KIND_LABELS[String(kind || '').toLowerCase()] || kind || 'Ansicht';

export const projectKindLabel = (kind) =>
  PROJECT_KIND_LABELS[String(kind || '').toLowerCase()] || kind || 'Modell';

export function relativeTime(value) {
  if (!value) return 'unbekannt';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'unbekannt';

  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'gerade eben';
  if (minutes < 60) return `vor ${minutes} Min.`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `vor ${hours} Std.`;

  const days = Math.floor(hours / 24);
  if (days === 1) return 'gestern';
  if (days < 7) return `vor ${days} Tagen`;

  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

export function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const rounded = size >= 10 || unit === 0 ? Math.round(size) : size.toFixed(1);
  return `${rounded} ${units[unit]}`;
}

export function formatDuration(ms) {
  if (ms == null) return '–';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1).replace('.', ',')} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes} min ${rest} s`;
}

export function isRunning(job) {
  return !!job && (job.status === 'queued' || job.status === 'running');
}