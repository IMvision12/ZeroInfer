// Render the public site and desktop surfaces offline; capture visual review files.
if (!process.versions.electron) {
  const child = require('node:child_process').spawn(require('electron'), [__filename], { stdio: 'inherit', windowsHide: true });
  child.on('error', error => { console.error(error); process.exitCode = 1; });
  child.on('exit', code => { process.exitCode = code ?? 1; });
} else {
  const { app, BrowserWindow, nativeTheme } = require('electron');
  const fs = require('node:fs');
  const path = require('node:path');
  const assert = require('node:assert/strict');
  const output = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'zeroinfer-theme-'));
  app.setPath('userData', path.join(output, 'profile'));
  app.commandLine.appendSwitch('disable-gpu');
  app.commandLine.appendSwitch('force-device-scale-factor', '1');
  app.commandLine.appendSwitch('force-prefers-reduced-motion');
  nativeTheme.themeSource = 'dark';
  app.whenReady().then(async () => {
    const win = new BrowserWindow({ width: 1440, height: 1000, show: false, webPreferences: { offscreen: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
    win.webContents.session.webRequest.onBeforeRequest({ urls: ['https://*/*', 'http://*/*'] }, (_details, cb) => cb({ cancel: true }));
    const js = code => win.webContents.executeJavaScript(code, true);
    const pause = () => new Promise(resolve => setTimeout(resolve, 150));
    const shot = async name => { await pause(); fs.writeFileSync(path.join(output, name + '.png'), (await win.webContents.capturePage()).toPNG()); };
    const load = file => win.loadFile(path.join(__dirname, '..', file));
    const palette = async () => js(`({background: getComputedStyle(document.body).backgroundColor, font: getComputedStyle(document.body).fontFamily, accent: getComputedStyle(document.documentElement).getPropertyValue('--zi-accent').trim()})`);
    await load('website/index.html');
    assert.equal(await js(`document.querySelector('#install') === null && document.querySelector('#first-run') === null`), true, 'Installation information belongs on the download page');
    const websitePalette = await palette();
    assert.notEqual(websitePalette.background, 'rgba(0, 0, 0, 0)', 'Theme stylesheet must load');
    assert.match(websitePalette.font, /Segoe UI/);
    for (const width of [1440, 768, 390, 320]) {
      win.setContentSize(width, 1000); await pause();
      await js('window.scrollTo({ top: 0, behavior: "instant" })');
      const overflow = await js(`({ viewport: innerWidth, width: document.documentElement.scrollWidth, elements: [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > innerWidth + 1).map(el => el.className).slice(0, 20) })`);
      assert.ok(overflow.width <= overflow.viewport, `Website overflow at ${width}px: ${JSON.stringify(overflow)}`);
      assert.equal(await js(`document.querySelector('.nav-cta').getBoundingClientRect().right <= innerWidth`), true, `Download button clipped at ${width}px`);
      await shot('website-' + width);
      assert.equal(await js(`document.querySelector('#hero-dl').getAttribute('href')`), 'download.html', 'Hero must open the download page');
      assert.equal(await js(`document.querySelector('.hero-copy #hero-dl') !== null && document.querySelector('#hero-cmd') === null`), true, 'Hero has one download button under its text');
      await js(`document.querySelector('.screenshot').scrollIntoView({behavior: 'instant', block: 'start'})`);
      assert.equal(await js(`(() => { const el = document.querySelector('.scr-main'); return el.scrollWidth <= el.clientWidth; })()`), true, `Preview contents clipped at ${width}px`);
      await shot('preview-' + width);
      if (width === 1440 || width === 390) {
        for (let i = 0; i < 3; i++) {
          await js(`document.querySelectorAll('.demo-story')[${i}].scrollIntoView({behavior: 'instant', block: 'center'})`);
          if (width === 1440) {
            const copyOnRight = await js(`(() => { const row = document.querySelectorAll('.demo-story')[${i}]; return row.querySelector('.demo-copy').getBoundingClientRect().left > row.querySelector('.demo-media').getBoundingClientRect().left; })()`);
            assert.equal(copyOnRight, i !== 1, 'Demo descriptions must alternate right/left/right');
          }
          await shot(`demo-${i + 1}-${width}`);
        }
      }
    }
    await js(`document.querySelector('#hero-dl').click()`);
    for (let i = 0; i < 40; i++) { if (await js(`!!document.querySelector('#platform-download')`)) break; await pause(); }
    assert.equal(await js(`!!document.querySelector('#platform-download')`), true, 'Download page must load from the hero');
    assert.equal(await js(`document.querySelectorAll('.platform-choices').length`), 1);
    assert.equal(await js(`document.querySelectorAll('.cmd').length`), 1, 'One installer command on the download page');
    assert.equal(await js(`document.querySelectorAll('.dl-btn').length`), 1, 'One primary download button');
    assert.equal(await js(`document.querySelector('#install') === null`), true, 'No duplicate installation section');
    await js(`Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => { window.copiedCommand = text; } } })`);
    for (const platform of ['windows', 'mac', 'linux']) {
      await js(`document.querySelector('[data-platform="${platform}"]').click()`);
      if (platform !== 'linux') {
        const asset = platform === 'windows' ? 'ZeroInfer-Setup.exe' : 'ZeroInfer.dmg';
        assert.equal(await js(`document.querySelector('#platform-download').href.split('/').pop()`), asset);
      }
      assert.equal(await js(`document.querySelectorAll('.platform-choice[aria-pressed="true"]').length`), 1);
      assert.equal(await js(`document.querySelector('#terminal-install').hidden`), false);
      assert.equal(await js(`document.querySelector('#manual-downloads').hidden`), platform !== 'linux');
      assert.equal(await js(`document.querySelector('#download-or').hidden`), platform === 'linux');
      assert.equal(await js(`document.querySelector('#platform-download').hidden`), platform === 'linux');
      assert.equal(await js(`document.querySelector('#windows-requirement').hidden`), platform !== 'windows');
      assert.equal(await js(`document.querySelector('#mac-build') === null`), true);
      assert.equal(await js(`document.querySelector('#first-run').tagName`), 'SECTION', 'First-launch instructions must always be visible');
      assert.equal(await js(`document.querySelectorAll('[data-help-platform]:not([hidden])').length`), 1);
      assert.equal(await js(`document.querySelector('[data-help-platform]:not([hidden])').dataset.helpPlatform`), platform);
      assert.equal(await js(`document.querySelector('#first-run').scrollWidth <= document.querySelector('#first-run').clientWidth`), true);
      await js(`document.querySelector('.download-command .cmd-copy').click()`); await pause();
      assert.equal(await js(`window.copiedCommand`), platform === 'windows'
        ? 'irm https://zeroinfer.vercel.app/install.ps1 | iex'
        : 'curl -fsSL https://zeroinfer.vercel.app/install.sh | sh');
      if (platform === 'linux') {
        await js(`document.querySelector('#manual-downloads summary').click()`);
        assert.equal(await js(`document.querySelector('#manual-downloads').open`), true);
        assert.deepEqual(await js(`[...document.querySelectorAll('.manual-download-links a')].map(a => a.href.split('/').pop())`), ['ZeroInfer.AppImage', 'ZeroInfer.deb']);
      }
      for (const [width, height] of [[1440, 900], [1366, 768], [1280, 720], [390, 1000], [320, 1000]]) {
        win.setContentSize(width, height); await pause();
        assert.equal(await js(`document.documentElement.scrollWidth <= innerWidth`), true, `Download page overflow: ${platform} at ${width}px`);
        if (width >= 1280) assert.equal(await js(`document.documentElement.scrollHeight <= innerHeight`), true, `Download page must fit without scrolling: ${platform} at ${width}x${height}`);
        assert.equal(await js(`(() => { const buttons = [...document.querySelectorAll('.platform-choice')].map(b => b.getBoundingClientRect()); return buttons.every(b => Math.abs(b.top - buttons[0].top) < 1) && document.querySelector('#platform-panel').getBoundingClientRect().top >= buttons[0].bottom; })()`), true, 'Platform info must expand below the horizontal OS selector');
        await shot(`download-${platform}-${width}`);
      }
    }
    win.setContentSize(900, 780);
    await js(`document.querySelector('#first-run').scrollIntoView({ behavior: 'instant', block: 'start' })`);
    await shot('download-installation-guide');
    for (const page of ['bootstrap', 'viewer']) {
      await load('src/main/' + page + '.html');
      assert.deepEqual(await palette(), { ...websitePalette, background: 'rgb(33, 33, 33)' }, `${page} must use the charcoal workspace with shared text and fonts`);
      await shot(page);
    }
    win.destroy();
    console.log('PASS: shared startup/viewer/website theme, system fonts, website responsive layout at 320/390/768/1440px.');
    console.log('Screenshots: ' + output);
    app.quit();
  }).catch(error => { console.error(error); app.exit(1); });
}
