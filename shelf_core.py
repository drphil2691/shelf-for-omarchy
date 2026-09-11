"""Local storage and clipboard helpers. No network access."""
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, unquote

MAX_ITEM_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000

def parse_uris(data):
    try:
        lines = data.decode('utf-8').splitlines()
        paths = []
        for line in lines:
            if not line or line.startswith('#'):
                continue
            uri = urlsplit(line)
            path = unquote(uri.path, errors='strict')
            if uri.scheme != 'file' or uri.netloc not in ('', 'localhost') or not path.startswith('/') or '\x00' in path or uri.query or uri.fragment:
                raise ValueError('Only local, absolute file URIs are supported')
            paths.append(path)
        if not paths:
            raise ValueError('No file URIs')
        return paths
    except (UnicodeError, TypeError) as exc:
        raise ValueError('Invalid URI list') from exc

def image_thumbnail(data):
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf, GLib
    loader = GdkPixbuf.PixbufLoader.new()
    dimensions = []
    def prepared(obj, width, height):
        dimensions.append((width, height))
        scale = min(128 / width, 96 / height, 1.0)
        obj.set_size(max(1, int(width * scale)), max(1, int(height * scale)))
    loader.connect('size-prepared', prepared)
    try:
        loader.write(data)
        loader.close()
        if not dimensions or dimensions[0][0] * dimensions[0][1] > MAX_IMAGE_PIXELS:
            raise ValueError('Image dimensions exceed 24 megapixels')
        return loader.get_pixbuf(), dimensions[0]
    except GLib.Error as exc:
        try:
            loader.close()
        except GLib.Error:
            pass
        raise ValueError('Invalid image') from exc

def validate(mime, data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_ITEM_BYTES:
        raise ValueError('Empty or oversized clipboard item (maximum 10 MiB)')
    if mime == 'text/plain':
        try:
            text = data.decode('utf-8')
        except UnicodeError as exc:
            raise ValueError('Text must be UTF-8') from exc
        if '\x00' in text:
            raise ValueError('Binary text is not supported')
        return text
    if mime == 'text/uri-list':
        return '\n'.join(parse_uris(data))
    if mime in ('image/png', 'image/jpeg', 'image/webp'):
        _, (width, height) = image_thumbnail(data)
        return f'Image · {width} × {height} · {mime.split("/")[1].upper()}'
    raise ValueError('Unsupported clipboard format')

class Store:
    def __init__(self, directory, max_items=200, max_bytes=100 * 1024 * 1024):
        self.max_items, self.max_bytes = max_items, max_bytes
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        path = self.directory / 'history.sqlite3'
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, mime TEXT NOT NULL, data BLOB NOT NULL, label TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0, touched INTEGER NOT NULL)')
        self.db.commit()

    def add(self, mime, data):
        import time
        label = validate(mime, data)
        with self.db:
            row = self.db.execute('SELECT id FROM items WHERE mime=? AND data=?', (mime, data)).fetchone()
            if row:
                ident = row['id']
                self.db.execute('UPDATE items SET touched=? WHERE id=?', (time.time_ns(), ident))
            else:
                ident = self.db.execute('INSERT INTO items(mime,data,label,touched) VALUES(?,?,?,?)', (mime, data, label, time.time_ns())).lastrowid
            self._prune()
        return ident

    def _prune(self):
        rows = self.db.execute('SELECT id,length(data) AS size FROM items WHERE pinned=0 ORDER BY touched DESC').fetchall()
        total = 0
        for index, row in enumerate(rows):
            total += row['size']
            if index >= self.max_items or total > self.max_bytes:
                self.db.execute('DELETE FROM items WHERE id=?', (row['id'],))

    def items(self, query=''):
        rows = self.db.execute('SELECT * FROM items ORDER BY pinned DESC,touched DESC')
        return [dict(row) for row in rows if query.casefold() in row['label'].casefold()]

    def pin(self, ident, pinned):
        with self.db:
            self.db.execute('UPDATE items SET pinned=? WHERE id=?', (int(pinned), ident))
            self._prune()

    def delete(self, ident):
        with self.db:
            self.db.execute('DELETE FROM items WHERE id=?', (ident,))

    def clear_unpinned(self):
        with self.db:
            self.db.execute('DELETE FROM items WHERE pinned=0')

    def get(self, ident):
        row = self.db.execute('SELECT * FROM items WHERE id=?', (ident,)).fetchone()
        return dict(row) if row else None

    def close(self):
        self.db.close()
