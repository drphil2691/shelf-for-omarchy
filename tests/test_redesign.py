"""Synthetic-only compact shelf regressions."""
import tempfile
import unittest
from unittest.mock import patch
from shelf_ui import ShelfApp
from gi.repository import Gtk, Gdk

class RedesignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.guard = patch('shelf_ui.active_window', return_value=None)
        self.guard.start()
        self.app = ShelfApp(self.tmp.name, paused=True)
        self.app.register(None)
        self.app.activate()

    def tearDown(self):
        self.app.shutdown_cleanly()
        self.app.window.destroy()
        self.guard.stop()
        self.tmp.cleanup()

    def test_double_click_copies_only_the_clicked_card(self):
        a = self.app
        ident = a.store.add('text/plain', b'SYNTHETIC double click')
        a.refresh()
        self.assertTrue(hasattr(a, 'card_pressed'), 'retain double-click copy')
        with patch('shelf_ui.copy_item') as copy:
            a.card_pressed(ident, 1)
            copy.assert_not_called()
            a.card_pressed(ident, 2)
            self.assertEqual(copy.call_args.args[0]['id'], ident)
            copy.assert_called_once()

    def test_link_validation_rejects_malformed_hosts_and_escape_sequences(self):
        from shelf_ui import item_kind
        invalid = ('https://exa%mple.org', 'https://-bad.example', 'https://bad..example',
                   'https://example.org\\\\evil', 'https://example.org/%ZZ', 'https://example.org/<tag>')
        for text in invalid:
            with self.subTest(text=text):
                self.assertEqual(item_kind({'mime': 'text/plain', 'label': text}), 'Text')
        for text in ('https://example.org/a%20b', 'http://localhost:8000/', 'https://[::1]/', 'https://例え.jp/'):
            with self.subTest(text=text):
                self.assertEqual(item_kind({'mime': 'text/plain', 'label': text}), 'Links')

    def test_default_focus_and_refresh_keep_keyboard_on_cards(self):
        a = self.app
        a.store.add('text/plain', b'SYNTHETIC focus')
        a.activate()
        self.assertIn(a.window.get_focus(), a.card_widgets.values())
        a.toggle_pin()
        self.assertIn(a.window.get_focus(), a.card_widgets.values())
        self.assertLessEqual(a.window.measure(Gtk.Orientation.VERTICAL, 760).minimum, 400)
        a.set_filter('Images')
        self.assertTrue(a.empty.get_vexpand())

    def test_capture_badge_survives_notifications_and_refresh_closes_stale_preview(self):
        a = self.app
        a.store.add('text/plain', b'SYNTHETIC only')
        a.refresh()
        with patch.object(a.monitor, 'start'), patch.object(a.monitor, 'stop'):
            a.set_capture(True)
            self.assertEqual(a.capture_state.get_text(), 'Capture on')
            a.notify('Copied.')
            self.assertEqual(a.capture_state.get_text(), 'Capture on')
            a.set_capture(False)
            self.assertEqual(a.capture_state.get_text(), 'Capture paused')
        a.open_preview()
        a.search.set_text('no matching synthetic item')
        a.refresh()
        self.assertIsNone(a.preview_window)
        self.assertFalse(a.handle_key(None, Gdk.KEY_Right, 0, Gdk.ModifierType(0)))

    def test_keyboard_preserves_editing_and_preview_lifecycle(self):
        a = self.app
        x = a.store.add('text/plain', b'SYNTHETIC one')
        y = a.store.add('text/plain', b'SYNTHETIC two')
        a.refresh()
        self.assertTrue(hasattr(a, 'handle_key'), 'keyboard browsing must be implemented')
        a.card_widgets[y].grab_focus()
        self.assertTrue(a.handle_key(None, Gdk.KEY_Right, 0, Gdk.ModifierType(0)))
        self.assertEqual(a.selected, x)
        with patch('shelf_ui.copy_item') as copy:
            self.assertTrue(a.handle_key(None, Gdk.KEY_Return, 0, Gdk.ModifierType(0)))
            copy.assert_called_once()
        self.assertIsNone(a.preview_window)
        self.assertTrue(a.handle_key(None, Gdk.KEY_space, 0, Gdk.ModifierType(0)))
        self.assertTrue(a.preview_window.get_visible())
        a.close_preview()
        self.assertIsNone(a.preview_window)
        a.handle_key(None, Gdk.KEY_f, 0, Gdk.ModifierType.CONTROL_MASK)
        a.search.set_text('two words')
        for key in (Gdk.KEY_space, Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Return):
            self.assertFalse(a.handle_key(None, key, 0, Gdk.ModifierType(0)))
        self.assertEqual(a.search.get_text(), 'two words')
        a.search.set_text('')
        a.refresh()
        a.open_preview()
        a.delete_selected()
        self.assertIsNone(a.preview_window)
        a.open_preview()
        a.hide_window()
        self.assertIsNone(a.preview_window)

    def test_compact_cards_selection_and_empty_state(self):
        a = self.app
        self.assertEqual(tuple(a.window.get_default_size()), (1080, 400))
        self.assertIsInstance(a.cards, Gtk.Box)
        self.assertEqual(a.cards.get_orientation(), Gtk.Orientation.HORIZONTAL)
        self.assertTrue(a.empty.get_visible())
        self.assertFalse(a.copy_button.get_sensitive())
        x = a.store.add('text/plain', b'SYNTHETIC one')
        y = a.store.add('text/plain', b'SYNTHETIC two')
        a.refresh()
        self.assertFalse(a.empty.get_visible())
        a.select(x)
        a.refresh()
        self.assertEqual(a.selected, x)
        self.assertTrue(a.card_widgets[x].has_css_class('selected'))
        self.assertFalse(a.card_widgets[y].has_css_class('selected'))
        a.window.set_default_size(760, 400)
        self.assertLessEqual(a.window.get_size_request().width, 760)
        a.delete_selected()
        self.assertEqual(a.selected, y)
        a.delete_selected()
        self.assertTrue(a.empty.get_visible())
        self.assertFalse(a.paste_button.get_sensitive())

    def test_filters_derive_whole_http_links_without_storage_changes(self):
        a = self.app
        link = a.store.add('text/plain', b'https://example.org/path?q=1')
        for text in (b'look https://example.org', b'https://', b'https://example.org two', b'https://example.org:bad', b'file:///tmp/demo'):
            a.store.add('text/plain', text)
        a.store.add('text/uri-list', b'file:///tmp/synthetic.txt')
        a.refresh()
        self.assertTrue(hasattr(a, 'set_filter'), 'compact shelf needs type filters')
        a.set_filter('Links')
        self.assertEqual(a.visible_count, 1)
        self.assertEqual(a.selected, link)
        a.toggle_pin()
        a.set_filter('Pinned')
        self.assertEqual(a.visible_count, 1)
        a.set_filter('Files')
        self.assertEqual(a.visible_count, 1)
        a.set_filter('Images')
        self.assertEqual(a.visible_count, 0)
        self.assertIsNone(a.selected)
        a.set_filter('Text')
        self.assertEqual(a.visible_count, 6)
        a.search.set_text('look')
        a.refresh()
        self.assertEqual(a.visible_count, 1)
