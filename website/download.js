// Stable asset names match electron-builder.yml. No release API is needed.
(() => {
  const base = 'https://github.com/ZeroAIx/ZeroInfer/releases/latest/download/';
  const platforms = {
    windows: { label: 'Windows', asset: 'ZeroInfer-Setup.exe' },
    mac: { label: 'macOS', asset: 'ZeroInfer.dmg' },
    linux: { label: 'Linux' },
  };
  const choices = [...document.querySelectorAll('[data-platform]')];
  const panel = document.getElementById('platform-panel');
  const detected = /mac/i.test(navigator.platform + navigator.userAgent) ? 'mac'
    : /linux/i.test(navigator.platform + navigator.userAgent) && !/android/i.test(navigator.userAgent) ? 'linux' : 'windows';
  const fromHash = () => Object.hasOwn(platforms, location.hash.slice(1)) ? location.hash.slice(1) : detected;
  let selected = fromHash();

  function render(animate = false) {
    const platform = platforms[selected];
    document.getElementById('platform-panel-title').textContent = `${platform.label} installation`;
    choices.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.platform === selected)));
    document.getElementById('terminal-install').hidden = false;
    document.getElementById('manual-downloads').hidden = selected !== 'linux';
    document.getElementById('download-or').hidden = selected === 'linux';
    const command = selected === 'windows'
      ? 'irm https://zeroinfer.vercel.app/install.ps1 | iex'
      : 'curl -fsSL https://zeroinfer.vercel.app/install.sh | sh';
    document.getElementById('download-command').dataset.copy = command;
    document.getElementById('download-command-text').textContent = command;
    document.getElementById('shell-hint').textContent = selected === 'windows' ? 'Paste this in PowerShell'
      : selected === 'mac' ? 'Paste this in Terminal' : 'Paste this in your terminal';
    document.getElementById('windows-requirement').hidden = selected !== 'windows';
    document.getElementById('launch-help-title').textContent = `First launch on ${platform.label}`;
    document.querySelectorAll('[data-help-platform]').forEach(help => {
      help.hidden = help.dataset.helpPlatform !== selected;
    });
    const link = document.getElementById('platform-download');
    link.hidden = selected === 'linux';
    if (platform.asset) link.href = base + platform.asset;
    else link.removeAttribute('href');
    link.textContent = `Download for ${platform.label}`;
    panel.getAnimations().forEach(animation => animation.cancel());
    if (animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      panel.animate([{ opacity: 0, transform: 'translateY(-8px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 200, easing: 'ease-out' });
    }
  }

  choices.forEach(button => {
    button.setAttribute('aria-controls', 'platform-panel');
    button.addEventListener('click', () => {
      const changed = selected !== button.dataset.platform;
      selected = button.dataset.platform;
      history.replaceState(null, '', '#' + selected);
      if (changed) {
        document.getElementById('manual-downloads').open = false;
      }
      render(changed);
    });
  });
  window.addEventListener('hashchange', () => {
    if (Object.hasOwn(platforms, location.hash.slice(1))) { selected = fromHash(); render(true); }
  });
  render();
})();
