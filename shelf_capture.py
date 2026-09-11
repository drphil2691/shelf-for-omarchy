"""Private, lifetime-scoped wl-paste watcher."""
import os
import signal
import subprocess
import sys
from pathlib import Path
from shelf_core import Store, MAX_ITEM_BYTES
from shelf_clipboard import capture_once


def ingest(directory, state):
    item = capture_once(state)
    if item:
        store = Store(directory)
        try:
            store.add(*item)
        finally:
            store.close()


class Monitor:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.command = 'wl-paste'
        self.process = None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if not self.running:
            self.process = subprocess.Popen(
                ['/usr/bin/python', str(Path(__file__).resolve()), '--watcher', str(self.directory), str(os.getpid()), self.command],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)

    def stop(self):
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
            self.process = None


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1] == '--watcher':
        import ctypes
        # Linux parent-death signal survives exec, including app SIGKILL/crash.
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or os.getppid() != int(sys.argv[3]):
            sys.exit(1)
        os.execvp(sys.argv[4], [sys.argv[4], '--watch', '/usr/bin/python', str(Path(__file__).resolve()), sys.argv[2]])
    # Never ingest unknown states: older wl-clipboard versions can lack hints.
    state = os.environ.get('CLIPBOARD_STATE', '')
    if state == 'data':
        # Drain only a bounded event payload. Re-read the preferred representation.
        event = sys.stdin.buffer.read(MAX_ITEM_BYTES + 1)
        if len(event) <= MAX_ITEM_BYTES:
            try:
                ingest(Path(sys.argv[1]), state)
            except Exception:
                # Deliberately do not log clipboard contents or provider errors.
                sys.exit(1)
