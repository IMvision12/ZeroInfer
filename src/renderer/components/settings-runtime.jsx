function settingsBytes(bytes) {
  if (bytes == null) return 'Not available';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let n = bytes, i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function RuntimeSettings({ hw, pyStatus, pySetup, runSetup }) {
  const [loaded, setLoaded] = React.useState([]);
  const [error, setError] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [confirm, setConfirm] = React.useState(null);
  const running = !!pySetup?.running;
  const isMac = pyStatus?.platform === 'darwin';
  const refresh = async () => {
    try { const r = await window.zeroinfer.tasks.loaded(); setLoaded(r.models || []); }
    catch (e) { setError(e.message); }
  };
  React.useEffect(() => { refresh(); }, []);
  const unload = async modelId => {
    setBusy(true); setError('');
    try { const r = await window.zeroinfer.tasks.unload(modelId); if (!r.ok) throw new Error(r.error); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return <>
    <div className="runtime-summary"><span className="integration-icon"><Icon name="cpu" size={23}/></span><div><strong>{running ? 'Installing runtime' : pyStatus?.ready ? 'Ready for inference' : 'Set up your runtime'}</strong><p>{running ? pySetup.step : pyStatus?.ready ? `PyTorch ${pyStatus.torch || ''} · ${pyStatus.installedAccelerator === 'gpu' ? isMac ? 'Apple Metal' : 'CUDA' : 'CPU'}` : 'Install the inference libraries to start running models.'}</p></div><span className={`s-pill ${pyStatus?.ready ? 'ok' : 'warn'}`}>{running ? 'Installing' : pyStatus?.ready ? 'Ready' : 'Setup needed'}</span></div>
    <SettingGroup title="Inference runtime">
      <SettingRow title={pyStatus?.ready ? 'Reinstall or change accelerator' : 'Install runtime'} sub="Downloads PyTorch and supporting libraries. Models remain on disk.">
        <div className="setting-actions"><button className="mc-btn ghost" disabled={running} onClick={() => setConfirm('cpu')}>{isMac ? 'Install / repair' : 'CPU'}</button>
          {!isMac && pyStatus?.hasNvidia && <button className="mc-btn primary" disabled={running} onClick={() => setConfirm('gpu')}>NVIDIA GPU</button>}</div>
      </SettingRow>
      <Notice error>{pySetup?.error}</Notice>
      {running && <div className="py-progress" role="progressbar" aria-label="Installing inference runtime"><div className="py-progress-bar"/></div>}
      {!!pySetup?.log?.length && <details className="setting-details"><summary>Installation log</summary><pre className="py-log">{pySetup.log.join('\n')}</pre></details>}
    </SettingGroup>
    <SettingGroup title="Loaded models" description="Unload a model to release its memory. Its downloaded files stay available.">
      {loaded.length ? loaded.map(id => <SettingRow key={id} title={id}><button className="mc-btn ghost" disabled={busy || running} onClick={() => unload(id)}>Unload</button></SettingRow>) : <p className="setting-empty">No models are currently loaded.</p>}
      <button className="settings-link" disabled={busy || running} onClick={refresh}>Refresh models</button><Notice error>{error}</Notice>
    </SettingGroup>
    <SettingGroup title="This device">
      <SettingRow title="Processor" sub={hw?.cpu?.brand || 'Not available'}/>
      <SettingRow title="Graphics" sub={hw?.gpu?.model || 'No supported GPU detected'}><span>{hw?.gpu?.memTotal ? settingsBytes(hw.gpu.memTotal) : ''}</span></SettingRow>
      <SettingRow title="Memory"><span>{settingsBytes(hw?.mem?.total)}</span></SettingRow>
      <SettingRow title="Disk space available"><span>{settingsBytes(hw?.disk?.free)}</span></SettingRow>
      <SettingRow title="Platform"><span>{[hw?.os?.distro || pyStatus?.platform, hw?.os?.arch || pyStatus?.arch].filter(Boolean).join(' · ') || 'Not available'}</span></SettingRow>
    </SettingGroup>
    <ConfirmDialog open={!!confirm} title="Install inference runtime?" message={`This downloads the ${isMac ? 'Apple Metal capable' : confirm === 'gpu' ? 'NVIDIA CUDA' : 'CPU'} runtime and restarts the inference engine. Loaded models will be released. Downloads may be several gigabytes.`} confirmLabel="Install runtime"
      onCancel={() => setConfirm(null)} onConfirm={() => { const accelerator = confirm; setConfirm(null); runSetup({ accelerator }); }}/>
  </>;
}

function DataSettings({ pyStatus, pySetup, refreshPyStatus, resetPySetup, onBusy }) {
  const [stats, setStats] = React.useState({});
  const [path, setPath] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState('');
  const [confirm, setConfirm] = React.useState('');
  const [step, setStep] = React.useState('');
  const [error, setError] = React.useState('');
  const [notice, setNotice] = React.useState('');
  const alive = React.useRef(true);
  const locked = React.useRef(false);
  const refresh = async () => {
    setLoading(true);
    const results = await Promise.allSettled(['hfCache', 'pyRuntime'].map(key => window.zeroinfer.storage.size(key)));
    if (!alive.current) return;
    const next = {};
    results.forEach((r, i) => {
      if (r.status === 'fulfilled' && r.value?.ok) next[i ? 'py' : 'hf'] = r.value;
      else setError('Some storage information could not be read. Try refreshing.');
    });
    setStats(next); setLoading(false);
  };
  React.useEffect(() => {
    alive.current = true; refresh();
    window.zeroinfer.logs.path().then(p => { if (alive.current) setPath(p); }).catch(e => { if (alive.current) setError(e.message); });
    return () => { alive.current = false; };
  }, []);
  const perform = async key => {
    if (locked.current) return;
    locked.current = true; setConfirm(''); setBusy(key); onBusy(true); setError(''); setNotice('');
    const off = key === 'py' ? window.zeroinfer.storage.onClearProgress(e => { if (e.kind === 'step') setStep(e.text); }) : null;
    try {
      const result = key === 'hf' ? await window.zeroinfer.storage.clearHfCache() : key === 'py' ? await window.zeroinfer.storage.clearPyRuntime() : await window.zeroinfer.chats.export();
      if (result?.cancelled) return;
      if (!result?.ok) throw new Error(result?.error || 'The operation failed.');
      if (result.errors?.length) throw new Error(`Some files could not be removed: ${result.errors.join('; ')}`);
      if (key === 'py') resetPySetup?.();
      setNotice(key === 'export' ? 'Sessions exported.' : key === 'hf' ? 'Model cache cleared.' : 'Inference runtime removed.');
    } catch (e) { setError(e.message || String(e)); }
    finally {
      off?.(); locked.current = false; setBusy(''); onBusy(false); setStep('');
      if (key !== 'export') { await refresh(); await refreshPyStatus?.(); }
    }
  };
  const disabled = !!busy || !!pySetup?.running;
  return <>
    <SettingGroup title="Sessions"><SettingRow title="Export your sessions" sub="Save conversations and task outputs as a JSON file. Tokens and settings are excluded."><button className="mc-btn ghost" disabled={disabled} onClick={() => perform('export')}><Icon name="download" size={14}/>{busy === 'export' ? 'Exporting…' : 'Export'}</button></SettingRow></SettingGroup>
    <SettingGroup title="Storage" description="Downloaded models use Hugging Face's cache, which may be shared with other applications.">
      <div className="storage-summary">{[['hf', 'Model cache'], ['py', 'Inference runtime']].map(([key, label]) => <div key={key}><span>{label}</span><strong>{loading ? 'Calculating…' : settingsBytes(stats[key]?.bytes)}</strong></div>)}</div>
      <SettingRow title="Model cache" sub={(stats.hf?.paths || [pyStatus?.hfCachePath]).filter(Boolean).join(' · ')}><button className="mc-btn ghost danger" disabled={disabled || loading || !stats.hf?.bytes} onClick={() => setConfirm('hf')}>Clear cache</button></SettingRow>
      <SettingRow title="Inference runtime" sub={busy === 'py' ? step || 'Removing runtime…' : 'Remove inference packages and cached wheels. Reinstall them to run models again.'}><button className="mc-btn ghost danger" disabled={disabled || loading || !stats.py?.bytes} onClick={() => setConfirm('py')}>Remove</button></SettingRow>
      <button className="settings-link" disabled={disabled || loading} onClick={() => { setError(''); refresh(); }}>Refresh storage usage</button>
    </SettingGroup>
    <SettingGroup title="Local files"><SettingRow title="App data folder" sub={path || 'Loading…'}><button className="mc-btn ghost" onClick={() => window.zeroinfer.logs.view().catch(e => setError(e.message))}>Open folder</button></SettingRow></SettingGroup>
    <Notice error>{error}</Notice><Notice>{notice}</Notice>
    <ConfirmDialog open={!!confirm} title={confirm === 'hf' ? 'Clear shared model cache?' : 'Remove inference runtime?'}
      message={confirm === 'hf' ? 'This permanently deletes downloaded model files from the detected Hugging Face caches, including models used by other apps. You will need to download them again. Sessions and settings are kept.' : 'This removes PyTorch, inference libraries, and cached installation files. Your model downloads and sessions are kept. You can reinstall from Runtime & hardware.'}
      confirmLabel={confirm === 'hf' ? 'Clear model cache' : 'Remove runtime'} danger onCancel={() => setConfirm('')} onConfirm={() => perform(confirm)}/>
  </>;
}
