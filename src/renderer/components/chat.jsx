const { useState: useStateCH, useEffect: useEffectCH, useRef: useRefCH } = React;

function titleFromFirstMessage(text, atts) {
  const cleaned = (text || '').trim().replace(/\s+/g, ' ');
  if (cleaned) {
    if (cleaned.length <= 60) return cleaned;
    const cut = cleaned.slice(0, 60);
    const lastSpace = cut.lastIndexOf(' ');
    return (lastSpace > 30 ? cut.slice(0, lastSpace) : cut).trimEnd() + '…';
  }
  const first = atts && atts[0];
  if (first?.name) {
    return first.name.replace(/\.[^.]+$/, '').replace(/[_\-]+/g, ' ');
  }
  return 'New chat';
}

const JANUS_MODES = [
  { value: 'understand', label: 'Understand', desc: 'Image in. text out' },
  { value: 'generate',   label: 'Generate',   desc: 'Text in. image out' },
];

function JanusModeBar({ value, onChange }) {
  return (
    <div className="whisper-bar">
      <div className="whisper-bar-head">
        <Icon name="sparkle" size={11}/>
        <span className="whisper-bar-k">Janus mode</span>
      </div>
      <div className="whisper-bar-toggle" role="radiogroup" aria-label="Janus mode">
        {JANUS_MODES.map(m => (
          <button
            key={m.value}
            type="button"
            role="radio"
            aria-checked={value === m.value}
            className={`whisper-pill ${value === m.value ? 'active' : ''}`}
            onClick={() => onChange(m.value)}
            title={m.desc}
          >
            <span className="whisper-pill-l">{m.label}</span>
            <span className="whisper-pill-d">{m.desc}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatWorkspace({ sessionId, modelId, modelMeta, onSaved, onBack, preferences = ZeroPreferences.defaults }) {
  const [chat, setChat] = useStateCH(null);
  const [input, setInput] = useStateCH('');
  const [atts, setAtts] = useStateCH([]);
  const [error, setError] = useStateCH(null);
  const [sending, setSending] = useStateCH(false);
  const [paramValues, setParamValues] = useStateCH(() => Object.fromEntries(GEN_PARAMS.map(p => [p.key, p.default])));


  const [stopping, setStopping] = useStateCH(false);
  const stoppedByUserRef = useRefCH(false);
  const stop = async () => {
    if (!sending || stopping) return;
    setStopping(true);
    stoppedByUserRef.current = true;
    try { await window.zeroinfer?.tasks?.stop?.(); } catch {}
  };
  const [janusMode, setJanusMode] = useStateCH('understand');
  const scrollRef = useRefCH(null);
  const inputRef = useRefCH(null);

  const isVLM = (modelMeta?.task === 'image-text-to-text');
  const isJanus = /janus/i.test(modelId || '');

  useEffectCH(() => {
    let cancelled = false;
    (async () => {
      if (!sessionId) return;
      let c;
      try { c = await window.zeroinfer.chats.get(sessionId); }
      catch (e) { if (!cancelled) setError(e.message); return; }
      if (!c && !cancelled) setError('This session could not be found. Open a model to start a new session.');
      if (cancelled || !c) return;

      const healed = (c.messages || []).map(m =>
        (m.streaming && !m.text)
          ? { ...m, streaming: false, text: '[interrupted]', error: true }
          : m
      );
      const changed = healed.some((m, i) => m !== (c.messages || [])[i]);
      const loaded = { ...c, messages: healed };
      if (changed) window.zeroinfer.chats.save(loaded).catch(e => {
        if (!cancelled) setError(`Could not save recovered conversation: ${e.message || e}`);
      });
      setChat(loaded);
      setParamValues(Object.fromEntries(GEN_PARAMS.map(p => [p.key, c.params?.[p.key] ?? p.default])));
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  useEffectCH(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [chat?.messages?.length]);

  useEffectCH(() => {
    if (inputRef.current) inputRef.current.focus();
  }, [sessionId]);

  if (!chat) return <div className="chat-view"><div className="chat-empty" role={error ? 'alert' : 'status'}>{error || 'Loading conversation…'}</div></div>;

  const send = async () => {
    const text = input.trim();
    const isGenerate = isJanus && janusMode === 'generate';
    if ((!text && !atts.length) || sending) return;
    for (const p of GEN_PARAMS) {
      if (p.type === 'boolean') continue;
      const value = paramValues[p.key];
      if (value === '' || !Number.isFinite(value) || value < p.min || value > p.max ||
          (p.type === 'number' && !Number.isInteger(value))) {
        setError(`${p.label} must be ${p.type === 'number' ? 'a whole number' : 'a number'} between ${p.min} and ${p.max}.`);
        return;
      }
    }


    if (isGenerate && !text) {
      setError('Generate mode needs a text prompt describing the image to create.');
      return;
    }
    if (!isGenerate) {
      const hasPriorImg = chat.messages.some(m => (m.attachments || []).some(a => a.kind === 'image'));
      if (isVLM && !atts.some(a => a.kind === 'image') && !hasPriorImg) {
        setError('This is a vision-language model. Attach an image before sending the first message.');
        return;
      }
    }
    setError(null);
    setSending(true);

    const userMsg = {
      id: 'u-' + Math.random().toString(36).slice(2),
      role: 'user',
      text,
      attachments: atts,
      ts: Date.now(),
    };
    const asstId = 'a-' + Math.random().toString(36).slice(2);
    const asstMsg = {
      id: asstId,
      role: 'assistant',
      text: '',
      ts: Date.now(),
      streaming: true,
      model: modelId,
    };
    const nextMsgs = [...chat.messages, userMsg, asstMsg];
    const baseTitle = chat.messages.length > 0 && chat.title && chat.title !== 'New chat'
      ? chat.title
      : titleFromFirstMessage(text, atts);
    const nextChat = {
      ...chat,
      title: baseTitle,
      modelId,
      task: modelMeta?.task,
      params: { ...paramValues },
      sub: `${modelId.split('/').pop()} · ${nextMsgs.length} msgs`,
      messages: nextMsgs,
    };
    try { await window.zeroinfer.chats.save(nextChat); }
    catch (e) {
      setError(`Could not save your message: ${e.message || e}`);
      setSending(false);
      return;
    }
    setChat(nextChat);
    setInput('');
    setAtts([]);
    onSaved && onSaved(nextChat);




    let imageAtt = isGenerate ? null : (atts || []).find(a => a.kind === 'image');
    if (!imageAtt && isVLM && !isGenerate) {
      for (let i = chat.messages.length - 1; i >= 0; i--) {
        const m = chat.messages[i];
        const prior = (m.attachments || []).find(a => a.kind === 'image');
        if (prior) { imageAtt = prior; break; }
      }
    }
    const task = modelMeta?.task || (isVLM ? 'image-text-to-text' : 'text-generation');
    const messages = ZeroPreferences.chatMessages(chat.messages, text, preferences);
    const sampling = !!paramValues.do_sample && paramValues.temperature > 0;
    const params = { max_new_tokens: paramValues.max_new_tokens, do_sample: sampling,
      ...(sampling ? { temperature: paramValues.temperature, top_p: paramValues.top_p, top_k: paramValues.top_k } : {}),
      ...(isJanus ? { janus_mode: janusMode } : {}) };
    const payload = {
      task,
      modelId,
      input: {
        // Vision adapters consume text directly; include the conversation in that
        // prompt. Text generators receive structured roles for their chat template.
        text: isVLM && !isGenerate ? messages.map(m => `${m.role}: ${m.content}`).join('\n\n') : text,
        ...(!isVLM && !isGenerate ? { messages } : {}),
        ...(imageAtt ? { dataUrl: imageAtt.dataUrl } : {}),
      },
      params,
    };

    const res = await window.zeroinfer.tasks.run(payload).catch(e => ({ ok: false, error: String(e?.message || e) }));

    const patchAssistant = async (patch) => {
      const done = { ...nextChat, messages: nextChat.messages.map(m =>
        m.id === asstId ? { ...m, ...patch, streaming: false } : m) };
      setChat(done);
      try {
        await window.zeroinfer.chats.save(done);
        onSaved && onSaved(done);
      } catch (e) {
        setError(`Reply is visible here but could not be saved: ${e.message || e}`);
      }
    };

    if (res?.ok) {
      const out = res.output || {};
      if (out.kind === 'image' && out.dataUrl) {
        await patchAssistant({ text: '', image: out.dataUrl });
      } else if (out.kind === 'text') {
        await patchAssistant({ text: out.text || '(empty reply)' });
      } else {
        await patchAssistant({ text: JSON.stringify(out) });
      }
    } else if (stoppedByUserRef.current) {
      await patchAssistant({ text: 'Stopped by user.', cancelled: true });
    } else {
      const errMsg = res?.error || 'inference failed';
      setError(errMsg);
      await patchAssistant({ text: errMsg, error: true });
    }
    stoppedByUserRef.current = false;
    setSending(false);
    setStopping(false);
  };

  const attachImage = async () => {
    try {
      const att = await window.zeroinfer.dialog.openImage();
      if (att) setAtts(a => [...a, att]);
    } catch (e) { setError(`Could not attach image: ${e.message || e}`); }
  };
  const removeAtt = (i) => setAtts(a => a.filter((_, idx) => idx !== i));

  const onKeyDown = (e) => {
    if (e.isComposing || e.nativeEvent?.isComposing) return;
    if (e.key === 'Enter' && !e.shiftKey && (preferences.sendOnEnter || e.ctrlKey || e.metaKey)) {
      e.preventDefault(); send();
    }
  };

  const visibleMessages = chat.messages.filter(m => m.role !== 'system');



  const hasPriorImage = chat.messages.some(m => (m.attachments || []).some(a => a.kind === 'image'));
  const isGenerateMode = isJanus && janusMode === 'generate';
  const vlmNeedsImage = !isGenerateMode && isVLM && atts.length === 0 && !hasPriorImage;
  const generateNeedsText = isGenerateMode && !input.trim();
  const sendDisabled = sending || vlmNeedsImage || generateNeedsText || (!input.trim() && atts.length === 0);

  return (
    <div className="chat-view">
      <div className="chat-head">
        <button type="button" className="workspace-back" onClick={onBack} aria-label="Back to models" title="Back to models"><Icon name="arrow_left" size={16}/> Back</button>
        <div className="chat-head-titles">
          <div className="chat-title">{chat.title || 'New chat'}</div>
          <div className="chat-sub">{modelId} · {visibleMessages.length} msg{visibleMessages.length === 1 ? '' : 's'}</div>
        </div>
        <div style={{flex:1}}/>
      </div>

      <div ref={scrollRef} className="chat-body">
        {visibleMessages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-ic"><Icon name={isJanus ? 'sparkle' : (isVLM ? 'eye' : 'chat')} size={28} stroke={1.4}/></div>
            <div className="chat-empty-t">{isJanus ? 'Janus' : (isVLM ? 'Vision-language chat' : 'Chat')}</div>
            <div className="chat-empty-s">
              {isJanus
                ? (isGenerateMode
                    ? <>Type a prompt. Janus will synthesize an image. Running <code>{modelId}</code> locally.</>
                    : <>Attach an image, then ask about it. Running <code>{modelId}</code> locally.</>)
                : (isVLM
                    ? <>Attach an image, then ask about it. Running <code>{modelId}</code> locally.</>
                    : <>Send a message. Running <code>{modelId}</code> locally.</>)}
            </div>
          </div>
        )}
        {visibleMessages.map(m => <Message key={m.id} m={m}/>)}
        {error && <div className="chat-err"><Icon name="alert" size={12}/> {error}</div>}
      </div>

      <div className="chat-composer">
        <ParamsPanel schema={GEN_PARAMS} values={paramValues} setValues={setParamValues} modelId={modelId}/>
        {isJanus && <JanusModeBar value={janusMode} onChange={setJanusMode}/>}
        {atts.length > 0 && (
          <div className="cc-atts">
            {atts.map((a, i) => (
              <div key={i} className="cc-att">
                {a.kind === 'image' && <img src={a.dataUrl} alt={a.name}/>}
                <span className="cc-att-nm">{a.name}</span>
                <button className="cc-att-x" onClick={() => removeAtt(i)}><Icon name="x" size={11}/></button>
              </div>
            ))}
          </div>
        )}
        <textarea
          ref={inputRef}
          className="cc-input"
          placeholder={
            isGenerateMode
              ? 'Describe the image you want Janus to generate…'
              : vlmNeedsImage
                ? 'Attach an image first, then ask about it…'
                : isVLM
                  ? 'Ask about the attached image…'
                  : 'Send a message…'
          }
          rows={2}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="cc-foot">
          {isVLM && !isGenerateMode && <button className="hp-chip" onClick={attachImage}><Icon name="paperclip" size={11}/> Image</button>}
          <span className="hp-hint">local · <span style={{color:'var(--fg-1)'}}>{modelId}</span></span>
          <div style={{flex:1}}/>
          <button
            className={`cc-send ${sending ? 'is-stop' : ''}`}
            onClick={sending ? stop : send}
            disabled={sending ? stopping : sendDisabled}
            title={sending ? 'Stop the running inference' : undefined}
          >
            {sending
              ? (stopping ? 'Stopping…' : <><Icon name="x" size={11}/> Stop</>)
              : <>Send <span className="cc-kbd">{preferences.sendOnEnter ? '↵' : /Mac/.test(navigator.platform) ? '⌘↵' : 'Ctrl ↵'}</span></>}
          </button>
        </div>
      </div>
    </div>
  );
}

function Message({ m }) {
  const images = (m.attachments || []).filter(a => a.kind === 'image');
  const saveGenerated = async () => {
    if (!m.image) return;
    try {
      const a = document.createElement('a');
      a.href = m.image;
      a.download = `janus-${m.id}.png`;
      a.click();
    } catch {}
  };
  return (
    <div className={`msg ${m.role}`}>
      <div className="msg-bubble">
        {images.length > 0 && (
          <div className="msg-imgs">
            {images.map((a, i) => <img key={i} src={a.dataUrl} alt={a.name}/>)}
          </div>
        )}
        {m.image && (
          <div className="msg-imgs msg-imgs-gen">
            <img src={m.image} alt="generated"/>
            <button type="button" className="msg-img-save" onClick={saveGenerated} title="Save image">
              <Icon name="download" size={12}/> Save
            </button>
          </div>
        )}
        {m.text && (
          m.role === 'assistant' && !m.error
            ? <MarkdownText text={m.text} className="msg-text"/>
            : <div className={`msg-text ${m.error ? 'err' : ''}`}>{m.text}</div>
        )}
        {m.streaming && !m.text && !m.image && (
          <div className="msg-loading">
            <span className="msg-dot"/><span className="msg-dot"/><span className="msg-dot"/>
            <span>running locally…</span>
          </div>
        )}
        <div className="msg-meta">{m.role === 'user' ? 'you' : (m.model || 'assistant')} · {formatTime(m.ts)}</div>
      </div>
    </div>
  );
}

const _markedConfigured = (() => {
  if (typeof window === 'undefined' || !window.marked) return false;
  try {
    window.marked.setOptions({
      gfm: true,    
      breaks: true, 
    });
  } catch { return false; }




  if (window.DOMPurify && typeof window.DOMPurify.addHook === 'function') {
    try {
      window.DOMPurify.addHook('afterSanitizeAttributes', (node) => {
        if (!node || node.nodeType !== 1) return;
        if (node.tagName === 'A') {
          node.setAttribute('target', '_blank');
          node.setAttribute('rel', 'noopener noreferrer');
        }
      });
    } catch {}
  }
  return true;
})();

function MarkdownText({ text, className }) {

  const html = React.useMemo(() => {
    if (!_markedConfigured || !window.DOMPurify) return null;
    try {
      const parsed = window.marked.parse(text || '', { async: false });
      return window.DOMPurify.sanitize(parsed, { ADD_ATTR: ['target', 'rel'] });
    } catch { return null; }
  }, [text]);


  if (html === null) {
    return <div className={className} style={{whiteSpace:'pre-wrap'}}>{text}</div>;
  }
  return <div className={`${className} markdown`} dangerouslySetInnerHTML={{ __html: html }}/>;
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

window.ChatWorkspace = ChatWorkspace;
