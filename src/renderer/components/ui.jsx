/* Shared accessible controls. Keep behavior consistent across app dialogs. */
function useDialogFocus(ref, open, onDismiss) {
  const dismiss = React.useRef(onDismiss);
  dismiss.current = onDismiss;
  React.useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const dialog = ref.current;
    if (!dialog) return;
    const nodes = () => Array.from(dialog.querySelectorAll('button, [href], input, select, textarea, [tabindex="0"]'))
      .filter(el => !el.disabled && el.getClientRects().length && !el.closest('[inert]'));
    (dialog.querySelector('[data-autofocus]') || nodes()[0] || dialog).focus();
    const key = e => {
      // Only the topmost dialog handles keys; child confirmations own their focus.
      const dialogs = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')];
      if (dialogs[dialogs.length - 1] !== dialog) return;
      if (e.key === 'Escape') {
        e.preventDefault(); e.stopPropagation(); dismiss.current?.();
      }
      if (e.key === 'Tab') {
        const all = nodes(), first = all[0], last = all[all.length - 1];
        if (!first) { e.preventDefault(); dialog.focus(); return; }
        if (e.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
          e.preventDefault(); first.focus();
        }
      }
    };
    document.addEventListener('keydown', key, true);
    return () => { document.removeEventListener('keydown', key, true); if (previous?.isConnected) previous.focus(); };
  }, [open]);
}

function SettingRow({ title, sub, children }) {
  return <div className="setting-row"><div className="setting-row-copy"><div className="setting-row-title">{title}</div>
    {sub && <div className="setting-row-description">{sub}</div>}</div><div className="setting-row-control">{children}</div></div>;
}

function SettingGroup({ title, description, children }) {
  return <section className="setting-group">{title && <h3>{title}</h3>}{description && <p className="setting-description">{description}</p>}{children}</section>;
}

function Toggle({ label, checked, onChange, disabled }) {
  return <button type="button" role="switch" aria-label={label} aria-checked={!!checked} disabled={disabled}
    className={`setting-switch ${checked ? 'is-on' : ''}`} onClick={() => onChange(!checked)}><span/></button>;
}

function Notice({ children, error = false }) {
  return children ? <div className={`setting-notice ${error ? 'is-error' : ''}`} role={error ? 'alert' : 'status'}>
    <Icon name={error ? 'alert' : 'check_c'} size={16}/><span>{children}</span></div> : null;
}

function CopyField({ label, value, multiline = false }) {
  const [state, setState] = React.useState('');
  const timer = React.useRef(null);
  React.useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    try {
      if (window.zeroinfer?.app?.copyText) await window.zeroinfer.app.copyText(value);
      else await navigator.clipboard.writeText(value);
      setState('Copied');
    } catch { setState('Copy failed'); }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState(''), 2200);
  };
  return <div className="copy-field"><div className="copy-field-label"><span>{label}</span>
    <button className="settings-link" type="button" onClick={copy} aria-label={`Copy ${label}`}>{state || 'Copy'}</button></div>
    {multiline ? <pre tabIndex="0">{value}</pre> : <code>{value}</code>}
    <span className="sr-only" role="status">{state}</span></div>;
}

class AppErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (this.state.error) return <div className="app-error" role="alert"><Icon name="alert" size={28}/>
      <h1>Something went wrong</h1><p>The interface could not finish loading. Reload to try again.</p>
      <details><summary>Error details</summary><pre>{String(this.state.error.message || this.state.error)}</pre></details>
      <button className="mc-btn primary" onClick={() => location.reload()}>Reload ZeroInfer</button></div>;
    return this.props.children;
  }
}
