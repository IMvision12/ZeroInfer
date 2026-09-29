function UpdateCheckButton({ currentVersion }) {
  const [state, setState] = useStateS('idle');
  const [result, setResult] = useStateS(null);
  const [progress, setProgress] = useStateS(0);   
  const [confirmOpen, setConfirmOpen] = useStateS(false);
  const openExternal = (url) => window.zeroinfer?.app?.openExternal?.(url);





  useEffectS(() => {
    let mounted = true;
    const u = window.zeroinfer?.updates;
    if (!u) return;
    const offProgress = u.onProgress?.((evt) => {
      if (!mounted) return;
      setProgress(Math.round(evt?.percent || 0));
      setState((s) => (s === 'downloading' || s === 'available' ? 'downloading' : s));
    });
    const offDownloaded = u.onDownloaded?.((evt) => {
      if (!mounted) return;
      setProgress(100);
      setResult((r) => ({ ...(r || {}), latestVersion: evt?.version || r?.latestVersion }));
      setState('downloaded');
    });
    const offError = u.onError?.((evt) => {
      if (!mounted) return;




      const errStr = evt?.error || 'Unknown error';
      setResult((r) => {
        const hadUpdate = !!(r && r.hasUpdate);
        return {
          ...(r || {}),
          error: errStr,
          ...(hadUpdate ? { canAutoUpdate: false } : {}),
        };
      });
      setState((s) => {
        if (s === 'downloading' || s === 'downloaded') return 'available';
        return 'idle';
      });
    });

    (async () => {
      if (!mounted) return;
      setState('checking');
      try {
        const r = await u.check?.();
        if (!mounted) return;
        if (!r || !r.ok) { setResult(r || { error: 'The update service did not respond.' }); setState('idle'); return; }
        setResult(r);
        setState(r.hasUpdate ? 'available' : 'uptodate');
      } catch (e) { if (mounted) { setResult({ error: e.message || String(e) }); setState('idle'); } }
    })();

    return () => {
      mounted = false;
      offProgress && offProgress();
      offDownloaded && offDownloaded();
      offError && offError();
    };
  }, []);

  const check = async () => {
    setState('checking');
    setProgress(0);
    try {

      const r = await window.zeroinfer?.updates?.check?.({ force: true });
      if (!r || !r.ok) {

        setResult(r || { error: 'unknown' });
        setState('idle');
        return;
      }
      setResult(r);
      setState(r.hasUpdate ? 'available' : 'uptodate');
    } catch (e) {
      setResult({ error: String(e?.message || e) });
      setState('idle');
    }
  };



  const requestDownload = () => setConfirmOpen(true);

  const confirmAndDownload = async () => {
    setConfirmOpen(false);
    setProgress(0);
    setState('downloading');
    try {
      const r = await window.zeroinfer?.updates?.download?.();
      if (!r) { setState('error'); setResult({ error: 'No response' }); return; }
      if (r.alreadyDownloaded) { setProgress(100); setState('downloaded'); return; }
      if (!r.ok) { setResult({ error: r.error || 'Download failed' }); setState('error'); return; }

    } catch (e) {
      setResult({ error: String(e?.message || e) });
      setState('error');
    }
  };

  const installAndRestart = async () => {
    setState('installing');



    window.dispatchEvent(new CustomEvent('zeroinfer:update-installing', {
      detail: { version: result?.latestVersion || '' },
    }));



    const timeoutId = setTimeout(() => {
      window.dispatchEvent(new CustomEvent('zeroinfer:update-install-failed'));
      setResult((r) => ({ ...(r || {}), error: 'Install timed out. Try downloading the installer manually from the website.' }));
      setState('idle');
    }, 30000);

    try {
      const response = await window.zeroinfer?.updates?.install?.();
      if (!response?.ok) throw new Error(response?.error || 'The update could not be installed.');
    }
    catch (e) {
      clearTimeout(timeoutId);
      setResult({ error: String(e?.message || e) });
      setState('error');
      window.dispatchEvent(new CustomEvent('zeroinfer:update-install-failed'));
    }

  };

  if (state === 'checking') {
    return (
      <button className="mc-btn ghost" disabled>
        <span className="upd-spin"/> Checking…
      </button>
    );
  }
  if (state === 'available' && result?.hasUpdate) {
    const canAuto = !!result.canAutoUpdate;
    return (
      <>
        <div className="upd-result">
          <span className="upd-tag mono">{result.latestVersion}</span>
          {canAuto ? (
            <button className="mc-btn primary" onClick={requestDownload}>
              <Icon name="arrow_right" size={11}/> Download
            </button>
          ) : (
            <button
              className="mc-btn primary"
              onClick={() => openExternal(result.downloadPageUrl || result.releaseUrl)}
            >
              <Icon name="arrow_right" size={11}/> Open download page
            </button>
          )}
        </div>
        <ConfirmDialog
          open={confirmOpen}
          title={`Download ZeroInfer ${result.latestVersion}?`}
          message="The update will download in the background. You'll be prompted to install and restart when it's ready."
          confirmLabel="Download"
          cancelLabel="Cancel"
          onConfirm={confirmAndDownload}
          onCancel={() => setConfirmOpen(false)}
        />
      </>
    );
  }
  if (state === 'downloading') {
    return (
      <div className="upd-result upd-result-col">
        <div className="upd-progress">
          <div className="upd-progress-bar" style={{ width: `${progress}%` }}/>
        </div>
        <span className="upd-tag mono">{progress}%</span>
      </div>
    );
  }
  if (state === 'downloaded') {
    return (
      <div className="upd-result">
        <span className="upd-tag mono">{result?.latestVersion || 'ready'}</span>
        <button className="mc-btn primary" onClick={installAndRestart}>
          <Icon name="arrow_right" size={11}/> Install &amp; restart
        </button>
      </div>
    );
  }
  if (state === 'installing') {
    return (
      <button className="mc-btn ghost" disabled>
        <span className="upd-spin"/> Restarting…
      </button>
    );
  }
  if (state === 'uptodate') {
    return (
      <button className="mc-btn ghost" onClick={check}>
        <Icon name="check_c" size={11}/> Up to date
      </button>
    );
  }
  return (
    <div className="update-check-result"><button className="mc-btn ghost" onClick={check}>
      <Icon name="arrow_right" size={11}/> Check for updates
    </button>{result?.error && <Notice error>{result.error}</Notice>}</div>
  );
}
