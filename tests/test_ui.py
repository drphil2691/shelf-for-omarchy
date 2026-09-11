"""GTK smoke: uses a disposable DB; never starts clipboard capture."""
import tempfile
import unittest
from unittest.mock import patch

class UiTests(unittest.TestCase):
    def test_paused_window_search_selection_and_hide(self):
        from shelf_ui import ShelfApp
        from gi.repository import GLib
        with tempfile.TemporaryDirectory() as tmp, patch('shelf_capture.Monitor.start', side_effect=AssertionError('must stay paused')):
            app = ShelfApp(tmp, paused=True)
            app.register(None)
            app.activate()
            ctx = GLib.MainContext.default()
            while ctx.pending():
                ctx.iteration(False)
            self.assertTrue(app.window.get_visible())
            self.assertFalse(app.monitor.running)
            a = app.store.add('text/plain', b'SYNTHETIC green apple')
            app.store.add('text/plain', b'SYNTHETIC blue sky')
            app.refresh()
            self.assertEqual(app.visible_count, 2)
            app.search.set_text('apple')
            app.refresh()
            self.assertEqual(app.visible_count, 1)
            app.select(a)
            self.assertEqual(app.selected, a)
            app.toggle_pin()
            self.assertTrue(app.store.get(a)['pinned'])
            app.delete_selected()
            self.assertIsNone(app.store.get(a))
            from gi.repository import Gtk
            app.search.set_text('')
            app.refresh()
            app.confirm_clear()
            dialog = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.MessageDialog))
            dialog.response(Gtk.ResponseType.CANCEL)
            self.assertEqual(len(app.store.items()), 1)
            app.confirm_clear()
            dialog = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.MessageDialog))
            dialog.response(Gtk.ResponseType.ACCEPT)
            self.assertEqual(app.store.items(), [])
            app.hide_window()
            self.assertFalse(app.window.get_visible())
            app.activate()
            self.assertTrue(app.window.get_visible())
            app.shutdown_cleanly()
            app.window.destroy()
