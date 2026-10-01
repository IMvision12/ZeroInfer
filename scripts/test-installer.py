"""Test the installer's real asset selection offline, stopping before installation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'website' / 'install.sh'


class InstallerSelection(unittest.TestCase):
    def select(self, system, arch, assets):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mocks = {
                'uname': '#!/bin/sh\ncase "$1" in -s) echo "$TEST_SYSTEM";; -m) echo "$TEST_ARCH";; esac\n',
                'curl': '#!/bin/sh\ncat "$TEST_RELEASE"\n',
                'python3': '#!/bin/sh\nexit 0\n',
            }
            for name, text in mocks.items():
                mock = root / name
                mock.write_text(text)
                mock.chmod(0o755)
            release = root / 'release.json'
            release.write_text(json.dumps({'assets': [
                {'browser_download_url': 'https://example.test/releases/' + name} for name in assets
            ]}))
            # Only execute detection and URL selection. No real network or install commands.
            script = root / 'select.sh'
            script.write_text(SOURCE.read_text().split('TMP="$(mktemp -d)"', 1)[0]
                              + '\nprintf "SELECTED=%s\\n" "$URL"\n')
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                       TEST_SYSTEM=system, TEST_ARCH=arch, TEST_RELEASE=str(release))
            return subprocess.run(['sh', str(script)], env=env, capture_output=True, text=True)

    def test_universal_preferred_for_both_mac_architectures(self):
        for arch in ['arm64', 'x86_64']:
            with self.subTest(arch=arch):
                result = self.select('Darwin', arch, ['ZeroInfer-arm64.zip', 'ZeroInfer-x64.zip', 'ZeroInfer.zip.blockmap', 'ZeroInfer.zip'])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('SELECTED=https://example.test/releases/ZeroInfer.zip\n', result.stdout)

    def test_legacy_mac_release_fallback(self):
        for arch, suffix in [('arm64', 'arm64'), ('x86_64', 'x64')]:
            with self.subTest(arch=arch):
                result = self.select('Darwin', arch, ['ZeroInfer-arm64.zip', 'ZeroInfer-x64.zip'])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'SELECTED=https://example.test/releases/ZeroInfer-{suffix}.zip\n', result.stdout)

    def test_linux_selects_appimage_not_blockmap(self):
        result = self.select('Linux', 'x86_64', ['ZeroInfer.AppImage.blockmap', 'ZeroInfer.deb', 'ZeroInfer.AppImage'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SELECTED=https://example.test/releases/ZeroInfer.AppImage\n', result.stdout)

    def test_missing_mac_archive_fails(self):
        result = self.select('Darwin', 'arm64', ['ZeroInfer-x64.zip', 'ZeroInfer.dmg'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no asset matching', result.stderr)

    def test_unsupported_linux_architecture_fails(self):
        result = self.select('Linux', 'aarch64', ['ZeroInfer.AppImage'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unsupported Linux architecture', result.stderr)


if __name__ == '__main__':
    unittest.main()
