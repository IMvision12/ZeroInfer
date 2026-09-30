/* Shared, dependency-free preferences and chat helpers. */
(function (root) {
  const defaults = Object.freeze({
    theme: 'dark', textSize: 'default', reduceMotion: false, showHardware: true,
    sendOnEnter: false, personalizationEnabled: true, nickname: '',
    customInstructions: '', responseStyle: 'default',
  });
  const themes = ['system', 'dark', 'light', 'nord', 'dracula', 'tokyo', 'catppuccin', 'gruvbox', 'onedark'];
  const styles = {
    default: '', concise: 'Use concise, direct answers. Include essential details.',
    friendly: 'Use a warm, conversational tone while staying accurate and useful.',
    technical: 'Use precise technical explanations and practical examples when helpful.',
  };
  function normalize(value = {}) {
    const p = { ...defaults, ...value };
    if (!themes.includes(p.theme)) p.theme = defaults.theme;
    if (!['small', 'default', 'large'].includes(p.textSize)) p.textSize = 'default';
    if (!Object.hasOwn(styles, p.responseStyle)) p.responseStyle = 'default';
    for (const k of ['reduceMotion', 'showHardware', 'sendOnEnter', 'personalizationEnabled']) {
      if (typeof p[k] !== 'boolean') p[k] = defaults[k];
    }
    p.nickname = typeof p.nickname === 'string' ? p.nickname.slice(0, 80) : '';
    p.customInstructions = typeof p.customInstructions === 'string' ? p.customInstructions.slice(0, 4000) : '';
    // Legacy global generation defaults no longer control individual models.
    delete p.maxNewTokens;
    delete p.temperature;
    return p;
  }
  function systemPrompt(preferences) {
    const p = normalize(preferences);
    if (!p.personalizationEnabled) return '';
    return [p.nickname.trim() && `The user's preferred name is ${p.nickname.trim()}.`,
      styles[p.responseStyle], p.customInstructions.trim()].filter(Boolean).join('\n\n');
  }
  function chatMessages(messages, text, preferences) {
    const system = systemPrompt(preferences);
    return [
      ...(system ? [{ role: 'system', content: system }] : []),
      ...messages.filter(m => ['user', 'assistant'].includes(m.role) && m.text && !m.error && !m.cancelled && !m.streaming)
        .map(m => ({ role: m.role, content: m.text })),
      { role: 'user', content: text },
    ];
  }
  const api = { defaults, themes, normalize, systemPrompt, chatMessages };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ZeroPreferences = api;
})(typeof window !== 'undefined' ? window : globalThis);
