/* Run with Electron after building. Tests the real renderer using an isolated
 * preload fixture; no model downloads, runtime installs, or user data access. */
const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'zeroinfer-ui-check-'));
app.setPath('userData', path.join(output, 'electron'));
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('force-device-scale-factor', '1');
let win;
const errors = [];
const js = code => win.webContents.executeJavaScript(code, true);
const pause = () => new Promise(r => setTimeout(r, 100));
async function waitFor(code) { for (let i = 0; i < 60; i++) { if (await js(code)) return; await pause(); } throw new Error(`Timed out: ${code}`); }
async function click(text, selector = 'button') {
  await js(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.textContent.trim() === ${JSON.stringify(text)}); if (!el) throw new Error('Button missing: ' + ${JSON.stringify(text)}); el.click(); })()`); await pause();
}
async function input(selector, value) {
  await js(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); })()`); await pause();
}
async function shot(name) { await pause(); fs.writeFileSync(path.join(output, name + '.png'), (await win.webContents.capturePage()).toPNG()); }
async function checkLayout() {
  const overflow = await js(`(() => { const card = document.querySelector('.settings-card'), body = document.querySelector('.settings-body'); const r = card.getBoundingClientRect(); return r.left < 0 || r.right > innerWidth || r.bottom > innerHeight || body.scrollWidth > body.clientWidth + 2; })()`);
  assert.equal(overflow, false, 'Settings must fit the viewport without horizontal overflow');
}
app.whenReady().then(async () => {
  win = new BrowserWindow({ width: 1280, height: 900, show: false, webPreferences: { offscreen: true, preload: path.join(__dirname, 'test-ui-preload.cjs'), contextIsolation: true, sandbox: false, nodeIntegration: false, backgroundThrottling: false } });
  win.webContents.on('console-message', (_e, level, message) => { if (level === 3) errors.push(message); });
  win.webContents.on('render-process-gone', (_e, details) => errors.push(JSON.stringify(details)));
  await win.loadFile(path.join(__dirname, '../src/renderer/dist/index.html'));
  await waitFor(`!!document.querySelector('.hub-landing')`);
  assert.equal((await js('window.__test.snapshot()')).calls.includes('save'), false, 'Mount must not overwrite saved preferences');
  await click('Settings', '.side-footer button');
  await waitFor(`!!document.querySelector('[role="dialog"]')`);
  await input('[aria-label="Theme"]', 'dark');
  await click('Save changes');
  await waitFor(`window.__test.snapshot().settings.theme === 'dark'`);
  assert.match(await js('getComputedStyle(document.body).fontFamily'), /Segoe UI/, 'Desktop must use the shared system font');
  assert.equal(await js(`getComputedStyle(document.querySelector('.main')).backgroundColor`), 'rgb(33, 33, 33)', 'Desktop must use the charcoal workspace');
  assert.equal(await js(`getComputedStyle(document.querySelector('.hub')).backgroundColor`), 'rgb(33, 33, 33)', 'Home must use the shared canvas');
  await click('Personalization', '.settings-nav-item');
  await input('[aria-label="Custom instructions"]', 'Use clear explanations and practical examples. Keep responses focused.');
  await input('#settings-nickname', 'Alex');
  await input('[aria-label="Response style"]', 'concise');
  await shot('settings-personalization');
  await checkLayout();
  assert.equal(await js(`document.querySelector('.settings-body').textContent.includes('Chat generation')`), false);
  await js(`document.querySelector('[aria-label="Close settings"]').click()`);
  await waitFor(`!!document.querySelector('[role="alertdialog"]')`);
  // A bubbled Enter must not invoke a global destructive confirmation handler.
  await js(`const cancel = document.querySelector('.confirm-actions button'); cancel.focus(); cancel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));`);
  assert.equal(await js(`!!document.querySelector('[role="alertdialog"]')`), true);
  await click('Cancel', '.confirm-actions button');
  await waitFor(`!document.querySelector('[role="alertdialog"]')`);
  assert.equal(await js(`!!document.querySelector('[role="dialog"]')`), true);
  await js(`window.__test.fail('save', 'Disk is full')`);
  await click('Save changes');
  assert.match(await js(`document.querySelector('.settings-save-status').textContent`), /Disk is full/);
  assert.equal((await js('window.__test.snapshot()')).settings.nickname, undefined);
  await js(`window.__test.fail('save', '')`);
  await click('Save changes');
  assert.equal((await js('window.__test.snapshot()')).settings.nickname, 'Alex');
  await click('Apps & integrations', '.settings-nav-item');
  await waitFor(`!!document.querySelector('.integration-guide')`);
  assert.match(await js(`document.querySelector('.integration-guide').textContent`), /ChatGPT desktop/);
  await input('[aria-label="API port"]', '80');
  await js(`document.querySelector('[aria-label="Enable local API"]').click()`); await pause();
  assert.match(await js(`document.querySelector('[role="alert"]').textContent`), /1024/);
  await input('[aria-label="API port"]', '11600');
  await js(`window.__test.fail('apiStart', 'Port is already in use'); document.querySelector('[aria-label="Enable local API"]').click()`); await pause();
  assert.match(await js(`document.querySelector('[role="alert"]').textContent`), /already in use/);
  await js(`window.__test.fail('apiStart', ''); document.querySelector('[aria-label="Enable local API"]').click()`); await pause();
  assert.equal((await js('window.__test.snapshot()')).api.port, 11600);
  await js(`window.__test.fail('copy', 'Clipboard unavailable'); document.querySelector('[aria-label="Copy Command"]').click()`); await pause();
  assert.equal(await js(`document.querySelector('[aria-label="Copy Command"]').textContent`), 'Copy failed');
  await js(`window.__test.fail('copy', ''); document.querySelector('[aria-label="Copy Command"]').click()`); await pause();
  assert.equal(await js(`document.querySelector('[aria-label="Copy Command"]').textContent`), 'Copied');
  await shot('settings-integrations');
  await checkLayout();
  await click('Runtime & hardware', '.settings-nav-item'); await pause();
  await click('Unload');
  assert.deepEqual((await js('window.__test.snapshot()')).loaded, []);
  await checkLayout();
  await click('Data controls', '.settings-nav-item'); await pause();
  await click('Export');
  assert.ok((await js('window.__test.snapshot()')).calls.includes('export'));
  await click('Clear cache');
  await click('Cancel', '.confirm-actions button');
  assert.equal((await js('window.__test.snapshot()')).calls.includes('clearCache'), false);
  await click('Hugging Face', '.settings-nav-item');
  await js(`window.__test.fail('clearToken', 'Token removal failed')`);
  await click('Clear');
  assert.match(await js(`document.querySelector('.py-card-err').textContent`), /Token removal failed/);
  await click('General', '.settings-nav-item');
  await input('[aria-label="Theme"]', 'light'); await click('Save changes');
  await shot('settings-general-light'); await checkLayout();
  await input('[aria-label="Theme"]', 'dark'); await click('Save changes');
  await shot('settings-general-dark');
  win.setSize(940, 640); await pause(); await checkLayout(); await shot('settings-compact');
  win.setSize(1280, 900); await pause();
  await js(`document.querySelector('[aria-label="Close settings"]').click()`); await pause();
  await shot('home');
  // A realistic suggestions list must scroll all the way past the final row.
  assert.equal(await js(`document.querySelectorAll('.hub-landing-col:last-child .hub-landing-row').length`), 5, 'Show at most five recommendations');
  for (const [width, height] of [[1280, 700], [940, 640]]) {
    win.setSize(width, height); await pause();
    const scroll = await js(`(() => {
      const hub = document.querySelector('.hub-idle');
      hub.scrollTop = hub.scrollHeight;
      const last = document.querySelector('.hub-landing-col:last-child .hub-landing-row:last-child').getBoundingClientRect();
      const bounds = hub.getBoundingClientRect();
      return { overflow: getComputedStyle(hub).overflowY, top: hub.scrollTop, visible: last.top >= bounds.top && last.bottom <= bounds.bottom - 16 && bounds.bottom <= innerHeight };
    })()`);
    assert.equal(scroll.overflow, 'auto', 'Home must allow mouse-wheel scrolling');
    assert.ok(scroll.top > 0, 'Long model lists must scroll');
    assert.equal(scroll.visible, true, `Last model must fit above bottom padding at ${width}x${height}`);
  }
  await shot('home-scrolled-bottom');
  win.setSize(1280, 900); await pause();
  await js(`document.querySelector('.hub-idle').scrollTop = 0`);
  await js(`window.__test.fail('download', 'Temporary connection failure'); document.querySelectorAll('.hub-landing-col')[1].querySelector('.hub-landing-row').click()`);
  await waitFor(`!!document.querySelector('.hub-landing-row-err')`);
  await js(`window.__test.fail('download', ''); document.querySelectorAll('.hub-landing-col')[1].querySelector('.hub-landing-row').click()`);
  await waitFor(`!document.querySelector('.hub-landing-row-err')`);
  assert.equal((await js('window.__test.snapshot()')).calls.filter(c => c === 'download').length, 2);
  await js(`window.__test.fail('search', 'Offline')`);
  await click('My models', '.new-chat-btn');
  await waitFor(`!!document.querySelector('.model-card')`);
  await input('.hub-search input', 'Qwen');
  await waitFor(`document.querySelectorAll('.model-card').length === 1`);
  assert.match(await js(`document.querySelector('.model-card').textContent`), /Qwen/);
  await js(`document.querySelector('.chat-item').click()`); await pause();
  await waitFor(`!!document.querySelector('.cc-input')`);
  await js(`document.querySelector('.chat-composer .tw-params').open = true`);
  await input('#p-max_new_tokens', '768');
  await input('#p-temperature', '0.35');
  await js(`document.querySelector('#p-do_sample').click()`); await pause();
  await input('.cc-input', 'What color did I mention?');
  await js(`window.__test.fail('chatSave', 'Disk is full'); document.querySelector('.cc-send').click()`); await pause();
  assert.match(await js(`document.querySelector('.chat-err').textContent`), /Could not save/);
  assert.equal(await js(`document.querySelector('.cc-input').value`), 'What color did I mention?');
  assert.equal((await js('window.__test.snapshot()')).calls.includes('run'), false);
  await js(`window.__test.fail('chatSave', '')`);
  await js(`document.querySelector('.cc-send').click()`); await pause();
  const payload = (await js('window.__test.snapshot()')).calls.find(x => x && typeof x === 'object' && x.input);
  assert.equal(payload.input.messages[0].role, 'system');
  assert.match(payload.input.messages[0].content, /Alex/);
  assert.equal(payload.input.messages.length, 4);
  assert.equal(payload.params.max_new_tokens, 768);
  assert.equal(payload.params.temperature, 0.35);
  assert.equal((await js('window.__test.snapshot()')).chat.params.max_new_tokens, 768);
  await js(`document.querySelector('.chat-composer .tw-params').open = false`);
  await shot('chat');
  await js(`window.zeroinfer.chats.patch('c-test', { title: 'hi' })`); await pause();
  assert.equal(await js(`document.querySelector('.chat-item .t1').textContent.trim()`), 'hi');
  assert.equal(await js(`document.querySelector('.chat-item-model').textContent`), 'Qwen3-0.6B');
  assert.equal(await js(`document.querySelector('.chat-item-model').title`), 'Qwen/Qwen3-0.6B');
  assert.equal(await js(`document.querySelector('.chat-item-task') === null`), true);
  await shot('recent-session-model');
  const savedChat = (await js('window.__test.snapshot()')).chat;
  await js(`document.querySelector('[aria-label="Back to models"]').click()`);
  await waitFor(`!!document.querySelector('.model-card')`);
  assert.equal(await js(`document.querySelector('.new-chat-btn.active').textContent.trim()`), 'My models');
  assert.deepEqual((await js('window.__test.snapshot()')).chat, savedChat, 'Back must preserve saved conversation');
  await js(`window.zeroinfer.chats.save({ id: 'detection-test', title: 'Detection example', kind: 'task', task: 'object-detection', modelId: 'facebook/detr-resnet-50', runs: [], createdAt: Date.now(), updatedAt: Date.now() })`);
  await pause();
  await js(`document.querySelector('.chat-item').click()`);
  await waitFor(`!!document.querySelector('.tw-head .workspace-back')`);
  await shot('inference-back');
  await js(`document.querySelector('[aria-label="Back to models"]').click()`);
  await waitFor(`!!document.querySelector('.model-card')`);
  assert.equal((await js('window.__test.snapshot()')).chat.id, 'detection-test');
  for (const [task, modelId, filename] of [
    ['object-detection', 'facebook/detr-resnet-50', 'pets.jpg'],
    ['mask-generation', 'facebook/sam-vit-base', 'zebras.png'],
    ['automatic-speech-recognition', 'openai/whisper-small', 'meeting.wav'],
  ]) {
    await js(`window.zeroinfer.chats.save(${JSON.stringify({ id: task, title: 'New session', kind: 'task', task, modelId, runs: [] })})`);
    await pause();
    await js(`document.querySelector('.chat-item').click()`);
    await waitFor(`!!document.querySelector('.tw-input-panel')`);
    assert.equal(await js(`document.querySelector('.chat-item .t1').textContent.trim()`), 'New session');
    await js(`document.querySelector('.tw-input-panel').click()`); await pause();
    await js(`document.querySelector('.tw .cc-send').click()`);
    await waitFor(`window.__test.snapshot().chat.runs?.[0]?.status === 'done'`);
    assert.equal((await js('window.__test.snapshot()')).chat.title, filename);
    assert.equal(await js(`document.querySelector('.chat-item .t1').textContent.trim()`), filename);
    assert.equal(await js(`document.querySelector('.chat-item-model').textContent`), modelId.split('/').pop());
    assert.equal(await js(`document.querySelector('.chat-item-task') === null`), true);
    await js(`document.querySelector('[aria-label="Back to models"]').click()`);
    await waitFor(`!!document.querySelector('.model-card')`);
  }
  assert.deepEqual(errors, [], 'Renderer console must have no errors');
  console.log('PASS: settings persistence, error states, API port, ChatGPT MCP setup, clipboard feedback, unload, export, keyboard cancellation, token errors, responsive layout, download retry, offline library, chat save recovery and history.');
  console.log(`Screenshots: ${output}`);
  win.destroy(); app.exit(0);
}).catch(async e => { console.error(e); if (win) await shot('failure').catch(() => {}); console.error(`Artifacts: ${output}`); app.exit(1); });
