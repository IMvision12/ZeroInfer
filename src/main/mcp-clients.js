'use strict';
const path = require('path');

// Desktop users paste separate command/argument fields; terminal users get
// a command quoted for their platform's default shell.
function mcpClients({ python, launcher, appData, platform = process.platform }) {
  const quote = value => `'${value.replace(/'/g, platform === 'win32' ? "''" : "'\\''")}'`;
  const command = cli => `${cli} mcp add zeroinfer -- ${quote(python)} ${quote(launcher)}`;
  return { clients: [
    {
      id: 'chatgpt', label: 'ChatGPT desktop',
      hint: 'The ChatGPT desktop app shares local MCP settings with its Codex host.',
      steps: ['Open a Codex chat in ChatGPT desktop, then open Settings → MCP servers → Add server.',
        'Choose STDIO and enter the fields below. Keep the command and argument in separate fields.',
        'Save the server, select Restart, then type /mcp in the Codex chat to verify the tools.',
        'Ordinary ChatGPT chats do not expose local Codex MCP servers. For those chats, use a remote MCP app or secure tunnel.'],
      fields: [{ label: 'Name', value: 'zeroinfer' }, { label: 'Command', value: python },
        { label: 'Argument', value: launcher }],
      docsUrl: 'https://learn.chatgpt.com/docs/extend/mcp',
    },
    { id: 'codex', label: 'Codex', copyLabel: 'Copy command', command: command('codex'),
      hint: 'Run once in a terminal. Uses the shared MCP configuration on this host.' },
    { id: 'claude', label: 'Claude Code', copyLabel: 'Copy command', command: command('claude'),
      hint: 'Run once in a terminal, then restart your Claude Code session.' },
    { id: 'claude-desktop', label: 'Claude Desktop', copyLabel: 'Copy config',
      hint: 'Merge this server into your existing configuration, then restart Claude Desktop.',
      value: path.join(appData, 'Claude', 'claude_desktop_config.json'),
      command: JSON.stringify({ mcpServers: { zeroinfer: { command: python, args: [launcher] } } }, null, 2) },
  ] };
}
module.exports = { mcpClients };
