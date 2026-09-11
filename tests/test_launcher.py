import subprocess
import unittest
from pathlib import Path

class LauncherTests(unittest.TestCase):
    def test_paused_single_instance_and_clean_termination(self):
        import tempfile
        import time
        import sqlite3
        launcher = Path(__file__).resolve().parents[1] / 'shelf'
        with tempfile.TemporaryDirectory() as tmp:
            command = [str(launcher), '--paused', '--data-dir', tmp]
            owner = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 8
                db = Path(tmp) / 'history.sqlite3'
                while not db.exists() and owner.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertIsNone(owner.poll(), 'paused app must remain running')
                self.assertTrue(db.exists())
                second = subprocess.run(command, capture_output=True, timeout=8)
                self.assertEqual(second.returncode, 0, second.stderr.decode())
                con = sqlite3.connect(db)
                try:
                    self.assertEqual(con.execute('SELECT count(*) FROM items').fetchone()[0], 0)
                finally:
                    con.close()
                children = Path('/proc') / str(owner.pid) / 'task' / str(owner.pid) / 'children'
                self.assertEqual(children.read_text().strip(), '', 'paused launcher must not spawn a watcher')
            finally:
                owner.terminate()
                _, errors = owner.communicate(timeout=8)
            self.assertEqual(owner.returncode, 0, errors.decode())

    def test_help_without_clipboard_access(self):
        launcher = Path(__file__).resolve().parents[1] / 'shelf'
        self.assertTrue(launcher.is_file(), 'executable launcher must exist')
        result = subprocess.run([str(launcher), '--help'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--paused', result.stdout)
        self.assertIn('--data-dir', result.stdout)
