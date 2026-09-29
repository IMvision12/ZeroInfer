function IntegrationSettings() {
  const [status, setStatus] = React.useState(null);
  const [clients, setClients] = React.useState([]);
  const [selected, setSelected] = React.useState('chatgpt');
  const [port, setPort] = React.useState('11500');
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const alive = React.useRef(true);
  const refresh = async () => {
    setError(''); setLoading(true);
    try {
      const [s, m] = await Promise.all([window.zeroinfer.api.status(), window.zeroinfer.api.mcpCommand()]);
      if (!alive.current) return;
      setStatus(s); setPort(String(s.port || 11500)); setClients(m.clients || []);
    } catch (e) { if (alive.current) setError(e.message || String(e)); }
    finally { if (alive.current) setLoading(false); }
  };
  React.useEffect(() => { alive.current = true; refresh(); return () => { alive.current = false; }; }, []);
  const toggle = async () => {
    const n = Number(port);
    if (!status?.running && (!Number.isInteger(n) || n < 1024 || n > 65535)) {
      setError('Choose a port between 1024 and 65535.'); return;
    }
    setBusy(true); setError('');
    try {
      const next = status?.running ? await window.zeroinfer.api.stop() : await window.zeroinfer.api.start(n);
      if (!alive.current) return;
      setStatus(next);
      if (next.error) setError(next.error);
      else if (!status?.running && !next.running) setError('The API did not start. Try another port.');
    } catch (e) { if (alive.current) setError(e.message || String(e)); }
    finally { if (alive.current) setBusy(false); }
  };
  const c = clients.find(c => c.id === selected) || clients[0];
  return <>
    <div className="integration-status"><span className={`connection-dot ${status?.running ? 'online' : ''}`}/><div><strong>Local API</strong><span>{loading ? 'Checking connection…' : status?.running ? 'Running on this device' : 'Not running'}</span></div>
      <Toggle label="Enable local API" checked={status?.running} onChange={toggle} disabled={busy || loading || !status}/></div>
    <SettingGroup>
      <SettingRow title="API port" sub={status?.running ? 'Turn off the API before changing its port.' : 'The API starts automatically next time if you leave it enabled.'}>
        <input type="number" className="setting-input short" aria-label="API port" min={1024} max={65535} value={port} disabled={loading || busy || status?.running} onChange={e => setPort(e.target.value)}/>
      </SettingRow>
      <CopyField label="OpenAI-compatible base URL" value={`${status?.url || `http://127.0.0.1:${port || 11500}`}/v1`}/>
      <p className="setting-description">Accepts any API key. The listener is restricted to this computer and has no authentication; other local applications can use it while enabled.</p>
      <Notice error>{error || status?.error}</Notice>
      <button className="settings-link" onClick={refresh} disabled={busy || loading}>{loading ? 'Checking…' : 'Refresh connection'}</button>
    </SettingGroup>
    <SettingGroup title="Connect an app" description="MCP gives your assistant access to local text, image, audio, and embedding models.">
      <div className="integration-clients" role="group" aria-label="MCP client">{clients.map(client => <button key={client.id} className={c?.id === client.id ? 'active' : ''} aria-pressed={c?.id === client.id} onClick={() => setSelected(client.id)}>{client.label}</button>)}</div>
      {c && <div className="integration-guide">
        <div className="integration-guide-title"><span className="integration-icon"><Icon name={c.id === 'chatgpt' ? 'sparkle' : 'layers'} size={21}/></span><div><h3>{c.label}</h3><p>{c.hint}</p></div></div>
        {!status?.running && <p className="integration-prerequisite"><Icon name="alert" size={15}/> Turn on the local API above before using these tools.</p>}
        {c.steps && <ol className="integration-steps">{c.steps.map(step => <li key={step}>{step}</li>)}</ol>}
        {c.fields?.map(field => <CopyField key={field.label} label={field.label} value={field.value} multiline={field.multiline}/>)}
        {c.value && <CopyField label="Configuration file" value={c.value}/>}
        {c.command && <CopyField label={c.copyLabel === 'Copy config' ? 'Configuration' : 'Terminal command'} value={c.command} multiline/>}
        {c.docsUrl && <button className="settings-link" onClick={() => window.zeroinfer.app.openExternal(c.docsUrl)}>Setup documentation <Icon name="arrow_right" size={13}/></button>}
      </div>}
      <p className="setting-description">Keep ZeroInfer running in the tray. Ask your assistant to call <code>zeroinfer_status</code> to verify the connection.</p>
    </SettingGroup>
  </>;
}
