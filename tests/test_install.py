import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def test_desktop_launch_treats_special_path_characters_literally(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'spaces "quotes" $dollar `tick` %f back\\slash'
            env = dict(os.environ, HOME=tmp, XDG_DATA_HOME=str(data))
            result = subprocess.run([sys.executable, str(ROOT / 'install.py')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            entry = data / 'applications/shelf-for-omarchy.desktop'
            subprocess.run(['desktop-file-validate', str(entry)], check=True)
            runtime = data / 'shelf-for-omarchy-app'
            # A synthetic executable proves argv handling without touching clipboard.
            (runtime / 'shelf').write_text("import json,sys\nfrom pathlib import Path\nPath(__file__).with_name('argv.json').write_text(json.dumps(sys.argv[1:]))\n")
            from gi.repository import Gio
            app = Gio.DesktopAppInfo.new_from_filename(str(entry))
            self.assertEqual(app.get_icon().get_file().get_path(), str(runtime / 'assets/shelf-for-omarchy.svg'))
            self.assertTrue(app.launch([], None))
            import time
            import json
            output = runtime / 'argv.json'
            deadline = time.monotonic() + 5
            while not output.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(output.exists(), 'desktop launch must reach the literal path')
            self.assertEqual(json.loads(output.read_text()), ['--paused'])

    def test_uninstall_leaves_history_and_upgrade_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            history = data / 'shelf-for-omarchy'
            history.mkdir(parents=True)
            private = history / 'history.sqlite3'
            private.write_bytes(b'synthetic private history')
            env = dict(os.environ, HOME=tmp, XDG_DATA_HOME=str(data))
            command = [sys.executable, str(ROOT / 'install.py')]
            subprocess.run(command, env=env, check=True, capture_output=True)
            runtime = data / 'shelf-for-omarchy-app'
            (runtime / 'previous-install-marker').write_text('preserve')
            subprocess.run(command, env=env, check=True, capture_output=True)
            backups = list(data.glob('shelf-for-omarchy-app.backup-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / 'previous-install-marker').read_text(), 'preserve')
            result = subprocess.run([sys.executable, str(runtime / 'install.py'), '--uninstall'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(runtime.exists())
            self.assertFalse((data / 'applications/shelf-for-omarchy.desktop').exists())
            self.assertTrue(backups[0].exists())
            self.assertEqual(private.read_bytes(), b'synthetic private history')

    def test_user_install_quotes_paths_preserves_history_and_validates(self):
        with tempfile.TemporaryDirectory(prefix='shelf install ') as tmp:
            home = Path(tmp) / 'home with spaces'
            data = home / '.local/share'
            history = data / 'shelf-for-omarchy'
            history.mkdir(parents=True)
            private = history / 'history.sqlite3'
            private.write_bytes(b'synthetic untouched history')
            before = private.stat()
            env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(data))
            result = subprocess.run([sys.executable, str(ROOT / 'install.py')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            entry = data / 'applications/shelf-for-omarchy.desktop'
            text = entry.read_text()
            self.assertIn('Name=Shelf for Omarchy', text)
            self.assertIn('Terminal=false', text)
            self.assertIn('--paused', text)
            self.assertNotIn('--data-dir', text)
            self.assertIn('"' + str(data / 'shelf-for-omarchy-app/shelf') + '"', text)
            subprocess.run(['desktop-file-validate', str(entry)], check=True)
            from gi.repository import Gio
            app = Gio.DesktopAppInfo.new_from_filename(str(entry))
            self.assertIsNotNone(app)
            self.assertEqual(app.get_name(), 'Shelf for Omarchy')
            runtime = data / 'shelf-for-omarchy-app'
            subprocess.run([sys.executable, str(runtime / 'shelf'), '--help'], check=True, capture_output=True)
            self.assertTrue((runtime / 'assets/shelf-for-omarchy.svg').is_file())
            self.assertEqual(private.read_bytes(), b'synthetic untouched history')
            self.assertEqual(private.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertFalse((home / '.config').exists())
