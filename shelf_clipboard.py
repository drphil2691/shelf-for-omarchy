"""Wayland utilities. Commands are argument arrays, never shell strings."""
import json
import os
import re
import selectors
import subprocess
import tempfile
import time
from shelf_core import MAX_ITEM_BYTES, validate


def read_limited(args, limit=MAX_ITEM_BYTES, input_data=None):
    """Read a child with a byte limit and a five-second deadline."""
    with tempfile.TemporaryFile() as source:
        if input_data is not None:
            source.write(input_data)
            source.seek(0)
        proc = subprocess.Popen(args, stdin=source if input_data is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        chunks, size, deadline = [], 0, time.monotonic() + 5
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ValueError('Clipboard command timed out')
                    chunk = os.read(proc.stdout.fileno(), min(65536, limit + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise ValueError('Clipboard data exceeds size limit')
                    chunks.append(chunk)
            if proc.wait(timeout=max(0.01, deadline - time.monotonic())):
                raise ValueError(f'{args[0]} failed; is the Wayland session available?')
            return b''.join(chunks)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()


def capture_once(state):
    if state != 'data':
        return None
    offered = read_limited(['wl-paste', '--list-types'], 16384).decode('utf-8', errors='replace').splitlines()
    if any('password' in mime.lower() or 'sensitive' in mime.lower() or 'secret' in mime.lower() for mime in offered):
        return None
    for mime in ('text/uri-list', 'image/png', 'image/jpeg', 'image/webp', 'text/plain;charset=utf-8', 'text/plain', 'UTF8_STRING'):
        if mime in offered:
            data = read_limited(['wl-paste', '--no-newline', '--type', mime])
            canonical = 'text/plain' if mime in ('UTF8_STRING', 'text/plain;charset=utf-8') else mime
            validate(canonical, data)
            return canonical, data
    return None


def copy_item(item):
    validate(item['mime'], item['data'])
    read_limited(['wl-copy', '--type', item['mime']], 16384, input_data=item['data'])


def active_window():
    try:
        return json.loads(read_limited(['hyprctl', '-j', 'activewindow'], 65536))
    except (OSError, ValueError):
        return None


def safe_target(target):
    if not isinstance(target, dict) or not re.fullmatch(r'0x[0-9a-fA-F]+', target.get('address', '')):
        return False
    cls = str(target.get('class', '')).lower()
    # Conservative: never auto-paste into known terminal/shell windows.
    blocked = ('terminal', 'alacritty', 'kitty', 'foot', 'wezterm', 'ghostty', 'konsole', 'xterm', 'st-256color', 'org.nous.shelf')
    return bool(target.get('pid') and cls and not any(word in cls for word in blocked))


def paste_to(target):
    if not safe_target(target):
        raise ValueError('No safe previous window. Copy instead, then paste manually.')
    clients = json.loads(read_limited(['hyprctl', '-j', 'clients'], 1024 * 1024))
    if not any(c.get('address') == target['address'] and c.get('pid') == target['pid'] and c.get('class') == target['class'] for c in clients):
        raise ValueError('The previous window has closed or changed. Nothing pasted.')
    # The config provider, not the version, determines dispatch syntax: new
    # Hyprland can still run a legacy config. Older releases lack `status`.
    try:
        status = json.loads(read_limited(['hyprctl', '-j', 'status'], 16384))
    except (OSError, ValueError):
        status = {}
    if isinstance(status, dict) and status.get('configProvider') == 'lua':
        command = ['hyprctl', 'dispatch',
                   'hl.dsp.focus({ window = "address:' + target['address'] + '" })']
    else:
        command = ['hyprctl', 'dispatch', 'focuswindow', 'address:' + target['address']]
    if read_limited(command, 16384).strip() != b'ok':
        raise ValueError('Could not focus the previous window. Nothing pasted.')
    time.sleep(0.15)
    current = active_window()
    if not current or any(current.get(k) != target.get(k) for k in ('address', 'pid', 'class')):
        raise ValueError('Could not verify focus on the previous window. Nothing pasted.')
    read_limited(['wtype', '-M', 'ctrl', '-k', 'v', '-m', 'ctrl'], 16384)
