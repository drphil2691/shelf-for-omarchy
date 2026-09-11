import tempfile
import unittest
from pathlib import Path

class StoreTests(unittest.TestCase):
    def test_byte_budget_and_pinned_duplicate(self):
        from shelf_core import Store
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp, max_items=100, max_bytes=7)
            first = store.add('text/plain', b'12345')
            second = store.add('text/plain', b'67890')
            self.assertIsNone(store.get(first))
            store.pin(second, True)
            self.assertEqual(store.add('text/plain', b'67890'), second)
            self.assertTrue(store.get(second)['pinned'])
            third = store.add('text/plain', b'abcdef')
            self.assertEqual(len(store.items()), 2)
            store.pin(second, False)
            self.assertEqual(len(store.items()), 1)
            self.assertIsNotNone(store.get(third))
            store.close()

    def test_database_symlink_is_rejected(self):
        from shelf_core import Store
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'untouched'
            target.write_text('DO NOT TOUCH')
            directory = Path(tmp) / 'data'
            directory.mkdir()
            (directory / 'history.sqlite3').symlink_to(target)
            with self.assertRaises(OSError):
                Store(directory)
            self.assertEqual(target.read_text(), 'DO NOT TOUCH')

    def test_bounded_deduplicated_pinned_history(self):
        from shelf_core import Store
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp, max_items=2, max_bytes=20)
            a = store.add('text/plain', b'alpha')
            self.assertEqual(a, store.add('text/plain', b'alpha'))
            store.pin(a, True)
            b = store.add('text/plain', b'beta')
            c = store.add('text/plain', b'gamma')
            store.add('text/plain', b'delta')
            self.assertIsNone(store.get(b))
            self.assertIsNotNone(store.get(a))
            self.assertEqual([r['id'] for r in store.items('ALPHA')], [a])
            store.clear_unpinned()
            self.assertEqual(len(store.items()), 1)
            store.delete(a)
            self.assertEqual(store.items(), [])
            store.close()

    def test_persistence_and_private_permissions(self):
        from shelf_core import Store
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data'
            store = Store(path)
            ident = store.add('text/plain', b'fresh synthetic note')
            store.close()
            store = Store(path)
            self.assertEqual(store.items()[0]['id'], ident)
            self.assertEqual(store.get(ident)['data'], b'fresh synthetic note')
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            self.assertEqual((path / 'history.sqlite3').stat().st_mode & 0o777, 0o600)
            store.close()
