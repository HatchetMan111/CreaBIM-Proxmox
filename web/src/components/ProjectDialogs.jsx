import { useRef, useState } from 'react';
import Dialog from './Dialog.jsx';
import { formatBytes } from '../format.js';

const ACCEPT = '.creabim,.creabim.json,.ifc,.ifcx,.json,.sh3d,.blend,.FCStd,.fcstd';

function FormError({ message }) {
  if (!message) return null;
  return (
    <div className="form-error" role="alert">
      {message}
    </div>
  );
}

export function NewProjectDialog({ info, busy, error, onClose, onCreate }) {
  const samples = info?.samples || [];
  const [name, setName] = useState('');
  const [sample, setSample] = useState(samples[0]?.key || 'starter');

  const submit = (event) => {
    event.preventDefault();
    if (busy) return;
    onCreate({ sample, name: name.trim() });
  };

  return (
    <Dialog
      title="Neues Projekt"
      description="Ein mitgeliefertes Beispielmodell ist der schnellste Start. Eigene Modelle lassen sich später importieren."
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Abbrechen
          </button>
          <button
            type="submit"
            form="new-project-form"
            className="btn btn-primary"
            disabled={busy}
          >
            {busy ? 'Wird angelegt …' : 'Projekt anlegen'}
          </button>
        </>
      }
    >
      <form id="new-project-form" onSubmit={submit}>
        <label className="field">
          <span>Name</span>
          <input
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="z. B. Wohnquartier Nord"
            maxLength={120}
            autoComplete="off"
          />
        </label>

        <div className="field">
          <span>Beispielmodell</span>
          {samples.length === 0 ? (
            <p className="muted">Gerade sind keine Beispielmodelle verfügbar.</p>
          ) : (
            <div className="sample-list">
              {samples.map((item) => (
                <label
                  key={item.key}
                  className={`sample-option ${sample === item.key ? 'is-selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="sample"
                    value={item.key}
                    checked={sample === item.key}
                    onChange={() => setSample(item.key)}
                  />
                  <span>
                    <strong>{item.name}</strong>
                    <small>{item.description}</small>
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>

        <FormError message={error} />
      </form>
    </Dialog>
  );
}

export function ImportDialog({ busy, error, onClose, onImport }) {
  const [file, setFile] = useState(null);
  const [name, setName] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  const pickFile = (files) => {
    const next = files && files[0];
    if (next) setFile(next);
  };

  const submit = (event) => {
    event.preventDefault();
    if (!file || busy) return;
    onImport({ file, name: name.trim() });
  };

  return (
    <Dialog
      title="Modell importieren"
      description="CreaBIM-Modelle, IFC/IFCX und JSON-Spezifikationen werden direkt eingelesen."
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Abbrechen
          </button>
          <button
            type="submit"
            form="import-form"
            className="btn btn-primary"
            disabled={!file || busy}
          >
            {busy ? 'Wird importiert …' : 'Importieren'}
          </button>
        </>
      }
    >
      <form id="import-form" onSubmit={submit}>
        <div
          className={`dropzone ${dragActive ? 'is-drag' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              inputRef.current?.click();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            pickFile(event.dataTransfer.files);
          }}
        >
          <p>
            <strong>Datei hier ablegen</strong> oder klicken
          </p>
          <p className="small">Erlaubt: .creabim, .creabim.json, .ifc, .ifcx, .json, .sh3d (Sweet Home 3D), .blend (Blender), .FCStd (FreeCAD)</p>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={(event) => pickFile(event.target.files)}
          />
        </div>

        {file && (
          <div className="file-chip">
            <span>
              {file.name} · {formatBytes(file.size)}
            </span>
            <button
              type="button"
              className="link-sm"
              onClick={() => {
                setFile(null);
                if (inputRef.current) inputRef.current.value = '';
              }}
            >
              Entfernen
            </button>
          </div>
        )}

        <label className="field">
          <span>Name (optional)</span>
          <input
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={file ? file.name.replace(/\.[^.]+$/, '') : 'Projektname'}
            maxLength={120}
            autoComplete="off"
          />
        </label>

        <FormError message={error} />
      </form>
    </Dialog>
  );
}

export function RenameDialog({ projectName, busy, error, onClose, onRename }) {
  const [name, setName] = useState(projectName);

  const submit = (event) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    onRename(trimmed);
  };

  return (
    <Dialog
      title="Projekt umbenennen"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Abbrechen
          </button>
          <button
            type="submit"
            form="rename-form"
            className="btn btn-primary"
            disabled={busy || !name.trim()}
          >
            {busy ? 'Wird gespeichert …' : 'Speichern'}
          </button>
        </>
      }
    >
      <form id="rename-form" onSubmit={submit}>
        <label className="field">
          <span>Name</span>
          <input
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            autoComplete="off"
          />
        </label>
        <FormError message={error} />
      </form>
    </Dialog>
  );
}

export function DeleteDialog({ projectName, busy, error, onClose, onDelete }) {
  return (
    <Dialog
      title="Projekt löschen"
      destructive
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Abbrechen
          </button>
          <button type="button" className="btn btn-danger" onClick={onDelete} disabled={busy}>
            {busy ? 'Wird gelöscht …' : 'Endgültig löschen'}
          </button>
        </>
      }
    >
      <p className="dialog-text">
        Das Projekt <strong>„{projectName}“</strong> wird mit Modell und allen
        Job-Artefakten vom Server gelöscht. Das lässt sich nicht rückgängig machen.
      </p>
      <FormError message={error} />
    </Dialog>
  );
}