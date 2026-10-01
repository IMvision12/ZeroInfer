# ZeroInfer website

Static landing page. No framework, no build step - just open `index.html` in a browser.

## Shared theme

The website, desktop renderer, startup screen, and output viewer use the palette
in `design/theme.json`. After editing it, run `npm run theme:sync` from the project
root. The renderer build also runs this automatically. Keep the generated
`theme.css` files with their respective pages; the website remains standalone.
Use the shared `--zi-*` variables for new colors and fonts.

The public page uses the black `canvas`; desktop windows and the embedded preview
use the charcoal `workspace`. Text and controls are neutral, with `action` reserved
for the primary website download button and semantic colors for statuses.

Run `npm run test:theme` for offline desktop/mobile layout checks and screenshots,
and `npm run test:ui` for the desktop app's interaction checks.
On Linux/macOS, run `python3 scripts/test-installer.py` from the project root to
test installer asset selection without downloading or installing anything.

## Universal macOS release

`npm run dist:mac` must run on macOS. It builds `ZeroInfer.dmg` for both Apple
Silicon and Intel, plus `ZeroInfer.zip` and update metadata for automatic updates.
The release workflow checks both architectures with `lipo` and requires these
artifacts before publication. Publish the new universal release before deploying
the updated website: its macOS button expects `ZeroInfer.dmg`.

## Structure

```
website/
├── index.html         # single-page landing
├── styles.css         # design tokens + sections
├── script.js          # shared clipboard controls and scroll effects
├── download.html      # platform selection and downloads
├── download.css       # responsive download page
├── download.js        # OS detection, processor selection, installer links
├── install.sh         # macOS/Linux installer  (curl -fsSL .../install.sh | sh)
├── install.ps1        # Windows installer      (irm .../install.ps1 | iex)
├── assets/
│   └── favicon.svg    # ZeroInfer constellation mark
└── README.md          # this file
```

## Two ways to install

The page offers both, because they suit different people: a **download button**
for anyone who just wants an app, and a **one-liner** for people who live in a
terminal. Both end up installing the exact same desktop build.

### Download button

The homepage Download button opens `download.html`. It selects the visitor's OS
and allows switching between Windows, macOS, and Linux using a horizontal selector.
Details expand below it. Windows offers an EXE; macOS offers one universal DMG
for Apple Silicon and Intel. Linux shows the install command with optional
AppImage and .deb files under Manual downloads (both x64).

Installer links use the stable asset filenames in `electron-builder.yml` under
`https://github.com/ZeroAIx/ZeroInfer/releases/latest/download/`. No release API
request is needed. A no-JavaScript fallback links to all release downloads.
macOS offers the terminal command above its universal download button. Linux
shows the same command, with optional manual downloads. Windows offers a PowerShell
command above its installer button.
Requirements appear once below the download. First-launch help stays visible for
the selected platform; changing platforms updates the help without adding
another installation section.

### Install scripts

`install.sh` and `install.ps1` are served as static files from the site root:

```
# Windows
irm https://zeroinfer.vercel.app/install.ps1 | iex
# macOS / Linux
curl -fsSL https://zeroinfer.vercel.app/install.sh | sh
```

Both resolve the latest release from the GitHub API, pick the asset matching the
host OS/arch, and install it:

| Platform | What the script does |
| --- | --- |
| Windows | downloads the `.exe` and runs it silently (`/S`, per-user, no admin), then launches the app |
| macOS | downloads universal `ZeroInfer.zip`, unpacks `ZeroInfer.app` into `/Applications`; falls back to older architecture-specific ZIPs before the universal release is available |
| Linux | downloads the `.AppImage` into `~/.local/bin` and adds a `.desktop` entry |

Each script checks for **Python 3.10+** and warns if it's missing, but installs
anyway - the app has a proper first-run screen for that case.

> On macOS the script is actually the *smoother* path: a file fetched with `curl`
> carries no `com.apple.quarantine` attribute, so Gatekeeper doesn't block the
> unsigned app the way it does when you download the `.dmg` in a browser.

> The scripts and the page hard-code `https://zeroinfer.vercel.app`. If you deploy
> to a different domain, update that host in `download.html`, `download.js`,
> and both installer scripts. Serving
> over **HTTPS** is required for `| iex` / `| sh`.

## Local preview

```bash
# any static server works
cd website
python -m http.server 8080
# or: npx serve
```

Open `http://localhost:8080`.
