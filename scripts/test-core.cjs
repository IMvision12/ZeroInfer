const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const preferences = require('../src/renderer/preferences');
const { mcpClients } = require('../src/main/mcp-clients');
const { writeMcpLauncher } = require('../src/main/mcp-setup');
const { PythonRunner } = require('../src/main/python-runner');

test('macOS release verification passes file before lipo architectures and propagates failures', () => {
  const vm = require('node:vm');
  const source = fs.readFileSync(path.join(__dirname, 'check-mac-universal.cjs'), 'utf8');
  function verify(failingBinary) {
    const calls = [], artifacts = [], messages = [];
    const context = {
      __dirname, process: { platform: 'darwin' },
      console: { log: message => messages.push(message) },
      require: name => {
        if (name === 'node:path') return path;
        if (name === 'node:fs') return { statSync: file => { artifacts.push(path.basename(file)); return { isFile: () => true }; } };
        if (name === 'node:child_process') return { execFileSync: (command, args) => {
          assert.equal(command, 'lipo');
          assert.ok(path.isAbsolute(args[0]), 'Input binary must come first');
          assert.deepEqual(Array.from(args.slice(1)), ['-verify_arch', 'x86_64', 'arm64']);
          calls.push(args[0]);
          if (calls.length === failingBinary) throw new Error('Missing architecture');
        } };
        throw new Error(`Unexpected dependency: ${name}`);
      },
    };
    return { run: () => vm.runInNewContext(source, context), calls, artifacts, messages };
  }
  const success = verify();
  success.run();
  assert.equal(success.calls.length, 2);
  assert.ok(success.calls[1].endsWith('Electron Framework'));
  assert.deepEqual(success.artifacts, ['ZeroInfer.dmg', 'ZeroInfer.zip', 'latest-mac.yml']);
  assert.equal(success.messages.length, 1);
  for (const binary of [1, 2]) {
    const failure = verify(binary);
    assert.throws(failure.run, /Missing architecture/);
    assert.equal(failure.messages.length, 0, 'Failed verification must not report success');
  }
});

test('personalization preserves history and excludes failed/interrupted turns', () => {
  const messages = preferences.chatMessages([
    { role: 'user', text: 'Remember blue' }, { role: 'assistant', text: 'OK' },
    { role: 'assistant', text: 'Failure', error: true }, { role: 'assistant', text: 'Partial', streaming: true },
  ], 'Which color?', { nickname: 'Alex', customInstructions: 'Be clear', responseStyle: 'concise' });
  assert.deepEqual(messages.map(m => m.role), ['system', 'user', 'assistant', 'user']);
  assert.match(messages[0].content, /Alex/);
  assert.match(messages[0].content, /Be clear/);
  assert.equal(preferences.systemPrompt({ personalizationEnabled: false, customInstructions: 'Be clear' }), '');
  assert.equal(preferences.normalize({ temperature: 0, maxNewTokens: 1024 }).temperature, undefined);
  assert.equal(preferences.normalize({ maxNewTokens: 1024 }).maxNewTokens, undefined);
});

test('MCP setup quotes unusual paths and preserves separate desktop fields', () => {
  const python = "C:\\Users\\O'Neil $data\\venv\\python.exe";
  const launcher = "C:\\Users\\O'Neil $data\\zeroinfer-mcp.py";
  const { clients } = mcpClients({ python, launcher, appData: 'C:\\Data', platform: 'win32' });
  assert.equal(clients[0].id, 'chatgpt');
  assert.equal(clients[0].fields[1].value, python);
  assert.ok(clients.find(c => c.id === 'codex').command.includes("O''Neil $data"));
  const config = JSON.parse(clients.find(c => c.id === 'claude-desktop').command);
  assert.equal(config.mcpServers.zeroinfer.command, python);
  assert.deepEqual(config.mcpServers.zeroinfer.args, [launcher]);
});

test('generated MCP launcher follows saved API port without changing user configuration', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'zi-launcher-'));
  fs.mkdirSync(path.join(root, 'mcp_server'));
  fs.writeFileSync(path.join(root, 'mcp_server', '__init__.py'), '');
  fs.writeFileSync(path.join(root, 'mcp_server', 'server.py'), 'import os\ndef main():\n    print(os.environ.get("ZEROINFER_URL"))\n');
  fs.writeFileSync(path.join(root, 'settings.json'), JSON.stringify({ apiPort: 11642 }));
  const launcher = writeMcpLauncher(root, root);
  const result = spawnSync('python', ['-B', launcher], { encoding: 'utf8', env: { ...process.env, ZEROINFER_URL: '' } });
  // Empty environment values are explicit overrides; remove the override to
  // test the normal client launch path.
  const env = { ...process.env }; delete env.ZEROINFER_URL;
  const normal = spawnSync('python', ['-B', launcher], { encoding: 'utf8', env });
  assert.equal(normal.status, 0, normal.stderr);
  assert.equal(normal.stdout.trim(), 'http://127.0.0.1:11642');
  assert.equal(result.status, 0, result.stderr);
});

test('stdio bridge preserves payload ids and rejects an engine that exits before ready', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'zi-protocol-'));
  const script = path.join(root, 'runner.py');
  fs.writeFileSync(script, 'import json,sys\nprint(json.dumps({"event":"ready"}),flush=True)\nfor line in sys.stdin:\n    msg=json.loads(line)\n    print(json.dumps({"id":msg["id"],"ok":True,"result":msg["payload"]}),flush=True)\n');
  const runner = new PythonRunner({ pythonPath: 'python', pythonDir: root, dataDir: root });
  assert.deepEqual(await runner.call('echo', { id: 'model-id', value: 7 }), { id: 'model-id', value: 7 });
  await runner.stopAndWait();
  fs.writeFileSync(script, 'raise SystemExit(4)\n');
  await assert.rejects(runner.start(), /before it was ready/);
});
