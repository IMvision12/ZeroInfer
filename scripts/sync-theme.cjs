// One palette for the static website, renderer and auxiliary desktop windows.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
function syncTheme() {
  const tokens = JSON.parse(fs.readFileSync(path.join(root, 'design/theme.json'), 'utf8'));
  const css = '/* Generated from design/theme.json. Run npm run theme:sync. */\n:root {\n  color-scheme: dark;\n' +
    Object.entries(tokens).map(([key, value]) => `  --zi-${key.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}: ${value};`).join('\n') + '\n}\n';
  for (const dir of ['website', 'src/renderer', 'src/main']) fs.writeFileSync(path.join(root, dir, 'theme.css'), css);
}
if (require.main === module) syncTheme();
module.exports = { syncTheme };
