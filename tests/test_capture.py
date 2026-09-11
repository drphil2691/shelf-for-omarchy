import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

class MonitorTests(unittest.TestCase):
    def test_watcher_dies_when_owner_exits(self):
        import subprocess
        import time
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'fake-watcher'
            fake.write_text('#!/usr/bin/python\nimport time\ntime.sleep(60)\n')
            fake.chmod(0o700)
            source = 'from shelf_capture import Monitor; import os,time; m=Monitor(' + repr(tmp) + '); m.command=' + repr(str(fake)) + '; m.start(); print(m.process.pid,flush=True); time.sleep(.2); os._exit(0)'
            owner = subprocess.run(['/usr/bin/python', '-c', source], capture_output=True, text=True, timeout=5)
            pid = int(owner.stdout.strip())
            time.sleep(.3)
            state = Path('/proc') / str(pid) / 'stat'
            dead = not state.exists() or state.read_text().split()[2] == 'Z'
            if not dead:
                os.kill(pid, 15)
            self.assertTrue(dead, 'watcher must not outlive the app even after abrupt exit')

    def test_paused_lifecycle_and_fixture_ingestion(self):
        from shelf_capture import Monitor, ingest
        from shelf_core import Store
        with tempfile.TemporaryDirectory() as tmp:
            monitor = Monitor(Path(tmp))
            self.assertFalse(monitor.running)
            fake = Path(tmp) / 'fake-wl-paste'
            fake.write_text('#!/usr/bin/python\nimport time\ntime.sleep(30)\n')
            fake.chmod(0o700)
            monitor.command = str(fake)
            monitor.start()
            self.assertTrue(monitor.running)
            monitor.stop()
            self.assertFalse(monitor.running)
            with patch('shelf_capture.capture_once', return_value=('text/plain', b'SYNTHETIC CAPTURE')):
                ingest(Path(tmp), 'data')
            store = Store(tmp)
            self.assertEqual(store.items()[0]['data'], b'SYNTHETIC CAPTURE')
            store.close()
