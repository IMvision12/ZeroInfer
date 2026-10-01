// Isolated fixture: never reads or writes the user's ZeroInfer data.
const { contextBridge } = require('electron');
const { mcpClients } = require('../src/main/mcp-clients');
const callbacks = {};
const on = key => fn => { (callbacks[key] ||= new Set()).add(fn); return () => callbacks[key].delete(fn); };
const emit = key => { for (const fn of callbacks[key] || []) fn(); };
let settings = { theme: 'nord', welcomeSeen: true };
let api = { running: false, enabled: false, port: 11500 };
let fail = {};
let calls = [];
let loaded = ['Qwen/Qwen3-0.6B'];
const status = { ready: true, runtimeInstalled: true, installedAccelerator: 'cpu', platform: 'win32', hasNvidia: true, torch: '2.6.0+cpu', runtimePath: 'C:\\ZeroInfer\\venv', hfCachePath: 'C:\\Models', arch: 'x64' };
const installed = { 'Qwen/Qwen3-0.6B': { task: 'text-generation', nm: 'Qwen3 0.6B', size: '1.2 GB' } };
let chat = { id: 'c-test', title: 'A local conversation', task: 'text-generation', modelId: 'Qwen/Qwen3-0.6B', kind: 'chat', messages: [{ role: 'user', text: 'My favorite color is blue.' }, { role: 'assistant', text: 'I will remember that.' }], createdAt: Date.now(), updatedAt: Date.now() };
const check = name => { calls.push(name); if (fail[name]) throw new Error(fail[name]); };
contextBridge.exposeInMainWorld('__test', { snapshot: () => ({ settings, api, calls, loaded, chat }), fail: (name, message) => { fail[name] = message; } });
contextBridge.exposeInMainWorld('zeroinfer', {
  dialog: {
    openImage: async () => ({ kind: 'image', name: chat.task === 'mask-generation' ? 'zebras.png' : 'pets.jpg', dataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aA1sAAAAASUVORK5CYII=' }),
    openAudio: async () => ({ kind: 'audio', name: 'meeting.wav', dataUrl: 'data:audio/wav;base64,' }),
  },
  settings: { get: async () => settings, save: async patch => { check('save'); settings = { ...settings, ...patch }; return settings; } },
  app: { version: async () => '2.4.0', openExternal: async () => {}, loginSettings: async () => ({ supported: true, enabled: false }), setLoginSettings: async enabled => ({ supported: true, enabled }), copyText: async () => { check('copy'); } },
  tasks: { status: async () => status, statusSync: () => status, loaded: async () => ({ models: loaded }), unload: async id => { check('unload'); loaded = loaded.filter(m => m !== id); return { ok: true }; },
    run: async payload => { check('run'); calls.push(payload); return { ok: true, output: { kind: 'text', text: 'Blue, as you mentioned earlier.' } }; }, stop: async () => ({ ok: true }), setup: async () => { check('setup'); return { ok: true }; },
    onSetupProgress: on('setup'), onDownloadProgress: on('download'), download: async () => { check('download'); return { ok: true }; }, cancelDownload: async () => ({ ok: true }) },
  hw: { get: async () => ({ cpu: { brand: 'Intel Core i7', cores: 8, threads: 16 }, mem: { total: 32 * 1024 ** 3, free: 18 * 1024 ** 3 }, gpu: { model: 'NVIDIA GeForce RTX 4070', memTotal: 12 * 1024 ** 3 }, disk: { free: 300 * 1024 ** 3 }, os: { distro: 'Windows 11', arch: 'x64' } }), subscribe: on('hw') },
  hf: { installed: async () => installed, search: async (_query, task) => { check('search'); return [!task || task === 'object-detection' ? { id: 'facebook/detr-resnet-50', nm: 'DETR ResNet 50', task: 'object-detection', size: '167 MB' } : { id: 'fixture/' + task, nm: 'Example ' + task, task, size: '150 MB' }]; }, modelInfo: async () => ({ bytes: 167000000 }), onInstallsChanged: on('installs'),
    markInstalled: async (id, meta) => { installed[id] = meta; emit('installs'); return true; },
    getToken: async () => 'hf_••••••test', setToken: async () => ({ ok: true }), verifyToken: async () => ({ ok: true, user: { name: 'local-user' } }), clearToken: async () => { check('clearToken'); return { ok: true }; } },
  chats: { list: async () => [chat], get: async () => chat, save: async c => { check('chatSave'); chat = c; emit('chats'); return { ok: true }; }, patch: async (_, patch) => { chat = { ...chat, ...patch }; emit('chats'); return { ok: true }; }, onUpdate: on('chats'), export: async () => { check('export'); return { ok: true }; } },
  api: { status: async () => api, start: async port => { check('apiStart'); return api = { running: true, enabled: true, port, url: `http://127.0.0.1:${port}` }; }, stop: async () => api = { ...api, running: false, enabled: false, url: null },
    mcpCommand: async () => mcpClients({ python: 'C:\\Users\\Example\\AppData\\Roaming\\ZeroInfer\\venv\\Scripts\\python.exe', launcher: 'C:\\Users\\Example\\AppData\\Roaming\\ZeroInfer\\zeroinfer-mcp.py', appData: 'C:\\Users\\Example\\AppData\\Roaming' }) },
  storage: { size: async key => ({ ok: true, bytes: key === 'hfCache' ? 8.2 * 1024 ** 3 : 3.6 * 1024 ** 3, paths: ['C:\\Local data\\ZeroInfer'] }), clearHfCache: async () => { check('clearCache'); return { ok: true }; }, clearPyRuntime: async () => { check('clearRuntime'); return { ok: true }; }, onClearProgress: on('clear') },
  logs: { path: async () => 'C:\\Users\\Example\\AppData\\Roaming\\ZeroInfer', view: async () => ({ ok: true }) },
  updates: { check: async () => ({ ok: true, hasUpdate: false }), onProgress: on('updateProgress'), onDownloaded: on('updated'), onError: on('updateError') },
});
