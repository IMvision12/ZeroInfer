const { useState: useStateS, useEffect: useEffectS } = React;

const SETTINGS_SECTIONS = [
  { id: 'general', label: 'General', icon: 'settings', description: 'Make ZeroInfer feel at home on your desktop.' },
  { id: 'personalization', label: 'Personalization', icon: 'pencil', description: 'Choose how your local chat models respond.' },
  { id: 'api', label: 'Apps & integrations', icon: 'layers', description: 'Connect your local models to the tools you use.' },
  { id: 'hardware', label: 'Runtime & hardware', icon: 'cpu', description: 'Manage the engine that runs your models.' },
  { id: 'data', label: 'Data controls', icon: 'folder', description: 'Your sessions, model downloads, and local storage.' },
  { id: 'hf', label: 'Hugging Face', icon: 'lock', description: 'Access private and gated models with your account.' },
];

function Settings({ open, onClose, initialSection, preferences, onSavePreferences, version, hw,
  pyStatus, pySetup, runSetup, refreshPyStatus, resetPySetup }) {
  const [section, setSection] = React.useState('general');
  const [draft, setDraft] = React.useState(() => ZeroPreferences.normalize(preferences));
  const [saved, setSaved] = React.useState(() => ZeroPreferences.normalize(preferences));
  const [saving, setSaving] = React.useState(false);
  const [maintenance, setMaintenance] = React.useState(false);
  const [error, setError] = React.useState('');
  const [notice, setNotice] = React.useState('');
  const [discard, setDiscard] = React.useState(false);
  const dialog = React.useRef(null);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const close = () => { if (saving || maintenance) return; if (dirty) setDiscard(true); else onClose(); };
  useDialogFocus(dialog, open, close);
  React.useEffect(() => {
    if (!open) return;
    const id = initialSection === 'appearance' ? 'general' : initialSection;
    setSection(SETTINGS_SECTIONS.some(s => s.id === id) ? id : 'general');
    const next = ZeroPreferences.normalize(preferences);
    setDraft(next); setSaved(next); setError(''); setNotice(''); setDiscard(false);
  }, [open, initialSection]);
  const change = patch => { setDraft(p => ({ ...p, ...patch })); setNotice(''); setError(''); };
  const save = async () => {
    if (saving) return;
    setSaving(true); setError('');
    try {
      const tokens = Number(draft.maxNewTokens), temperature = Number(draft.temperature);
      if (!String(draft.maxNewTokens).trim() || !Number.isInteger(tokens) || tokens < 16 || tokens > 8192)
        throw new Error('Maximum response tokens must be a whole number between 16 and 8,192.');
      if (!String(draft.temperature).trim() || !Number.isFinite(temperature) || temperature < 0 || temperature > 2)
        throw new Error('Temperature must be a number between 0 and 2.');
      const next = ZeroPreferences.normalize(draft);
      const patch = Object.fromEntries(Object.entries(next).filter(([key, value]) => value !== saved[key]));
      await onSavePreferences(patch);
      setDraft(next); setSaved(next); setNotice('Changes saved.');
    } catch (e) { setError(e.message || String(e)); }
    finally { setSaving(false); }
  };
  if (!open) return null;
  const active = SETTINGS_SECTIONS.find(s => s.id === section);
  return <div className="settings-modal" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}>
    <div ref={dialog} className="settings-card" role="dialog" aria-modal="true" aria-labelledby="settings-title" tabIndex={-1}>
      <aside className="settings-nav">
        <div className="settings-nav-top"><button data-autofocus className="settings-close" aria-label="Close settings" onClick={close} disabled={saving || maintenance}><Icon name="x" size={19}/></button><span>Settings</span></div>
        <nav aria-label="Settings categories">{SETTINGS_SECTIONS.map(s => <button key={s.id}
          className={`settings-nav-item ${section === s.id ? 'active' : ''}`} aria-label={s.label} title={s.label} aria-current={section === s.id ? 'page' : undefined}
          disabled={maintenance || saving} onClick={() => { setSection(s.id); setError(''); setNotice(''); }}>
          <Icon name={s.icon} size={17}/><span>{s.label}</span></button>)}</nav>
        <div className="settings-nav-footer"><Logo size={24}/><div>ZeroInfer<span>Version {version || '—'}</span></div></div>
      </aside>
      <div className="settings-content">
        <header className="settings-header"><h2 id="settings-title">{active.label}</h2><p>{active.description}</p></header>
        <div className="settings-body" key={section} inert={saving ? '' : undefined}>
          {section === 'general' && <GeneralSettings draft={draft} change={change} version={version}/>}
          {section === 'personalization' && <PersonalizationSettings draft={draft} change={change}/>}
          {section === 'api' && <IntegrationSettings/>}
          {section === 'hardware' && <RuntimeSettings hw={hw} pyStatus={pyStatus} pySetup={pySetup} runSetup={runSetup}/>}
          {section === 'data' && <DataSettings pyStatus={pyStatus} pySetup={pySetup} refreshPyStatus={refreshPyStatus} resetPySetup={resetPySetup} onBusy={setMaintenance}/>}
          {section === 'hf' && <SettingGroup title="Account access" description="Your token is stored on this computer and used to authenticate requests to Hugging Face."><HFTokenCard/></SettingGroup>}
        </div>
        <footer className="settings-footer"><div className="settings-save-status" role={error ? 'alert' : 'status'}>
          {error || (maintenance ? 'Storage operation in progress…' : dirty ? 'You have unsaved changes' : notice || 'Preferences are stored on this device')}
        </div>{dirty && <button className="mc-btn ghost" disabled={saving || maintenance} onClick={() => { setDraft(saved); setError(''); }}>Cancel</button>}
          <button className="mc-btn primary" disabled={!dirty || saving || maintenance} onClick={save}>{saving ? 'Saving…' : 'Save changes'}</button></footer>
      </div>
      <ConfirmDialog open={discard} title="Discard unsaved changes?" message="Your changes to preferences have not been saved."
        confirmLabel="Discard changes" onConfirm={() => { setDiscard(false); onClose(); }} onCancel={() => setDiscard(false)}/>
    </div>
  </div>;
}

function GeneralSettings({ draft, change, version }) {
  const [startup, setStartup] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  React.useEffect(() => {
    let alive = true;
    window.zeroinfer.app.loginSettings().then(s => { if (alive) setStartup(s); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, []);
  const login = async enabled => {
    setBusy(true); setError('');
    try { setStartup(await window.zeroinfer.app.setLoginSettings(enabled)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return <>
    <SettingGroup title="Appearance">
      <SettingRow title="Theme" sub="Use your system appearance or choose a theme."><select aria-label="Theme" className="setting-select" value={draft.theme} onChange={e => change({ theme: e.target.value })}>
        {[['system', 'System'], ['dark', 'Dark'], ['light', 'Light'], ['nord', 'Nord'], ['dracula', 'Dracula'], ['tokyo', 'Tokyo Night'], ['catppuccin', 'Catppuccin'], ['gruvbox', 'Gruvbox'], ['onedark', 'One Dark']].map(([v, label]) => <option key={v} value={v}>{label}</option>)}
      </select></SettingRow>
      <div className="appearance-previews" aria-hidden="true">{['light', 'dark', 'system'].map(t => <div key={t} className={`appearance-preview ${t} ${draft.theme === t ? 'selected' : ''}`}><div className="preview-window"><aside/><main><i/><i/><i/><b/></main></div><span>{t === 'system' ? 'Match system' : t === 'dark' ? 'Dark' : 'Light'}</span></div>)}</div>
      <SettingRow title="Conversation text size"><select aria-label="Conversation text size" className="setting-select" value={draft.textSize} onChange={e => change({ textSize: e.target.value })}>{['small', 'default', 'large'].map(v => <option key={v} value={v}>{v[0].toUpperCase() + v.slice(1)}</option>)}</select></SettingRow>
      <SettingRow title="Reduce motion" sub="Minimize animations throughout the app."><Toggle label="Reduce motion" checked={draft.reduceMotion} onChange={v => change({ reduceMotion: v })}/></SettingRow>
    </SettingGroup>
    <SettingGroup title="Desktop">
      <SettingRow title="Launch at login" sub={startup?.supported === false ? 'Available in installed Windows and macOS apps.' : 'Start quietly in the system tray when you sign in.'}><Toggle label="Launch at login" checked={startup?.enabled} disabled={!startup?.supported || busy} onChange={login}/></SettingRow>
      <SettingRow title="Hardware monitor" sub="Show CPU, memory, and GPU usage in the sidebar."><Toggle label="Hardware monitor" checked={draft.showHardware} onChange={v => change({ showHardware: v })}/></SettingRow>
      <SettingRow title="Send with Enter" sub="When off, use Ctrl+Enter or ⌘+Enter. Shift+Enter always adds a line."><Toggle label="Send with Enter" checked={draft.sendOnEnter} onChange={v => change({ sendOnEnter: v })}/></SettingRow>
      <p className="setting-description">Closing the window keeps models available in the tray. Use Quit ZeroInfer in the tray menu to shut down the engine.</p>
    </SettingGroup>
    <SettingGroup title="About"><SettingRow title={`ZeroInfer ${version || ''}`} sub="Local models. One workspace."><UpdateCheckButton currentVersion={version}/></SettingRow>
      <SettingRow title="Help & feedback"><button className="settings-link" onClick={() => window.zeroinfer.app.openExternal('https://github.com/ZeroAIx/ZeroInfer/issues')}>Report an issue <Icon name="arrow_right" size={13}/></button></SettingRow>
    </SettingGroup><Notice error>{error}</Notice>
  </>;
}

function PersonalizationSettings({ draft, change }) {
  return <>
    <SettingRow title="Enable personalization" sub="Apply your preferences to conversations in ZeroInfer."><Toggle label="Enable personalization" checked={draft.personalizationEnabled} onChange={v => change({ personalizationEnabled: v })}/></SettingRow>
    <fieldset className="personalization-fields" disabled={!draft.personalizationEnabled}>
      <SettingRow title="Response style" sub="Set the tone for your local chat models."><select className="setting-select" aria-label="Response style" value={draft.responseStyle} onChange={e => change({ responseStyle: e.target.value })}>
        <option value="default">Default</option><option value="concise">Concise</option><option value="friendly">Friendly</option><option value="technical">Technical</option>
      </select></SettingRow>
      <SettingGroup title="Custom instructions" description="What should your models know about how you would like them to respond?">
        <textarea className="setting-textarea" aria-label="Custom instructions" placeholder="For example: explain concepts clearly, include practical examples, and ask when something is unclear."
          rows={5} maxLength={4000} value={draft.customInstructions} onChange={e => change({ customInstructions: e.target.value })}/>
        <div className="setting-field-hint">Used with each chat message. Model support and adherence may vary.<span>{draft.customInstructions.length.toLocaleString()} / 4,000</span></div>
      </SettingGroup>
      <SettingGroup title="About you"><label className="setting-label" htmlFor="settings-nickname">Nickname</label><input id="settings-nickname" className="setting-input" maxLength={80} placeholder="What should models call you?" value={draft.nickname} onChange={e => change({ nickname: e.target.value })}/></SettingGroup>
    </fieldset>
    <SettingGroup title="Chat generation" description="Defaults for text responses in the chat workspace.">
      <SettingRow title="Maximum response tokens" sub="Longer responses take more time and memory."><input className="setting-input short" type="number" aria-label="Maximum response tokens" min={16} max={8192} step={16} value={draft.maxNewTokens} onChange={e => change({ maxNewTokens: e.target.value })}/></SettingRow>
      <SettingRow title="Temperature" sub="Lower values are more predictable. Zero uses greedy decoding."><input className="setting-input short" type="number" aria-label="Temperature" min={0} max={2} step={0.1} value={draft.temperature} onChange={e => change({ temperature: e.target.value })}/></SettingRow>
    </SettingGroup>
  </>;
}
