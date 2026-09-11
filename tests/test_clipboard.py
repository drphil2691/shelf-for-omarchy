import unittest
import tempfile

class ClipboardTests(unittest.TestCase):
    def test_image_thumbnail_preserves_aspect_ratio(self):
        import gi
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf
        from shelf_core import image_thumbnail, validate
        original = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 320, 200)
        original.fill(0x83dec8ff)
        _, data = original.save_to_bufferv('png', [], [])
        thumb, dimensions = image_thumbnail(bytes(data))
        self.assertEqual(dimensions, (320, 200))
        self.assertEqual((thumb.get_width(), thumb.get_height()), (128, 80))
        self.assertIn('320 × 200', validate('image/png', bytes(data)))

    def test_capture_state_priority_and_bounded_process_io(self):
        from shelf_clipboard import capture_once, read_limited, copy_item
        import os
        import sys
        from unittest.mock import patch
        commands = []
        def run(args, limit=0, input_data=None):
            commands.append((args, input_data))
            if '--list-types' in args:
                return b'text/plain\ntext/uri-list\n'
            return b'file:///tmp/synthetic%20fixture'
        with patch('shelf_clipboard.read_limited', run):
            self.assertIsNone(capture_once('sensitive'))
            self.assertIsNone(capture_once('nil'))
            self.assertEqual(commands, [])
            self.assertEqual(capture_once('data'), ('text/uri-list', b'file:///tmp/synthetic%20fixture'))
            copy_item({'mime': 'text/plain', 'data': b'$(not a command)'})
            self.assertEqual(commands[-1], (['wl-copy', '--type', 'text/plain'], b'$(not a command)'))
        self.assertEqual(read_limited([sys.executable, '-c', 'print("synthetic")'], 20), b'synthetic\n')
        with self.assertRaises(ValueError):
            read_limited([sys.executable, '-c', 'print("x" * 10000)'], 10)
        with patch('shelf_clipboard.read_limited', return_value=b'text/plain\nx-kde-passwordManagerHint\n'):
            self.assertIsNone(capture_once('data'))

    def test_explicit_paste_target_guard(self):
        from shelf_clipboard import paste_to, safe_target
        from unittest.mock import patch
        import json
        target = {'address': '0xabc', 'pid': 100, 'class': 'SyntheticEditor', 'title': 'fixture'}
        self.assertTrue(safe_target(target))
        self.assertFalse(safe_target(dict(target, **{'class': 'Alacritty'})))
        self.assertFalse(safe_target(dict(target, address='bad;command')))
        self.assertFalse(safe_target(None))
        calls = []
        def run(args, limit=0, input_data=None):
            calls.append(args)
            if args == ['hyprctl', '-j', 'clients']:
                return json.dumps([target]).encode()
            if args == ['hyprctl', '-j', 'activewindow']:
                return json.dumps(target).encode()
            return b'ok'
        with patch('shelf_clipboard.read_limited', run):
            paste_to(target)
        self.assertIn(['hyprctl', 'dispatch', 'focuswindow', 'address:0xabc'], calls)
        self.assertEqual(calls[-1], ['wtype', '-M', 'ctrl', '-k', 'v', '-m', 'ctrl'])
        with self.assertRaises(ValueError):
            paste_to(None)

    def test_validate_payloads_and_local_uris(self):
        from shelf_core import validate, parse_uris, Store, MAX_ITEM_BYTES
        self.assertEqual(validate('text/plain', b'hello'), 'hello')
        self.assertEqual(parse_uris(b'#comment\r\nfile:///tmp/a%20b\r\nfile://localhost/tmp/x\n'), ['/tmp/a b', '/tmp/x'])
        self.assertIn('a b', validate('text/uri-list', b'file:///tmp/a%20b'))
        for mime, data in [('text/plain', b''), ('text/plain', b'\xff'), ('text/plain', b'a\x00b'), ('text/plain', b'x' * (MAX_ITEM_BYTES + 1)), ('image/png', b'bad'), ('application/executable', b'no'), ('text/uri-list', b'https://example.com'), ('text/uri-list', b'file://remote/tmp/x'), ('text/uri-list', b'file:///tmp/a%00b')]:
            with self.subTest(mime=mime, size=len(data)):
                with self.assertRaises(ValueError):
                    validate(mime, data)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            with self.assertRaises(ValueError):
                store.add('text/plain', b'\xff')
            self.assertEqual(store.items(), [])
            store.close()
