// Run after packaging on macOS, before the draft release can be published.
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
if (process.platform !== 'darwin') throw new Error('Universal binary verification requires macOS.');
const output = path.resolve(__dirname, '../dist-app');
const app = path.join(output, 'mac-universal/ZeroInfer.app/Contents');
for (const binary of ['MacOS/ZeroInfer', 'Frameworks/Electron Framework.framework/Versions/A/Electron Framework']) {
  execFileSync('lipo', ['-verify_arch', 'x86_64', 'arm64', path.join(app, binary)], { stdio: 'inherit' });
}
for (const file of ['ZeroInfer.dmg', 'ZeroInfer.zip', 'latest-mac.yml']) {
  if (!fs.statSync(path.join(output, file)).isFile()) throw new Error(`Missing macOS release artifact: ${file}`);
}
console.log('PASS: universal macOS binaries, installer, update archive and metadata.');
