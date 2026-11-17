import { useEffect } from 'react';

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const icon =
    toast.kind === 'success' ? '✓' : toast.kind === 'warn' ? '!' : '×';

  return (
    <div className={`toast toast-${toast.kind}`} role="status">
      <span className="toast-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="toast-msg">{toast.message}</span>
      <button
        type="button"
        className="toast-close"
        onClick={() => onDismiss(toast.id)}
        aria-label="Hinweis schließen"
      >
        ×
      </button>
    </div>
  );
}

export default function Toasts({ toasts, onDismiss }) {
  return (
    <div className="toasts" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}