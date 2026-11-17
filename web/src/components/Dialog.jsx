import { useEffect, useRef } from 'react';

// Basiskomponente für alle Dialoge: Backdrop-Klick und Escape schließen,
// der Fokus landet im ersten Eingabefeld und kehrt danach zurück.
export default function Dialog({
  title,
  description,
  children,
  footer,
  onClose,
  wide = false,
  destructive = false,
}) {
  const panelRef = useRef(null);

  useEffect(() => {
    const handleKey = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', handleKey);

    const previous = document.activeElement;
    const focusTarget = panelRef.current?.querySelector(
      'input:not([type="hidden"]), select, textarea, button',
    );
    if (focusTarget) focusTarget.focus();

    document.body.classList.add('modal-open');

    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.classList.remove('modal-open');
      if (previous && typeof previous.focus === 'function') previous.focus();
    };
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className={`dialog ${wide ? 'dialog-wide' : ''} ${destructive ? 'dialog-destructive' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="dialog-head">
          <h2>{title}</h2>
          {description && <p className="dialog-desc">{description}</p>}
        </div>
        <div className="dialog-body">{children}</div>
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </div>
  );
}