"""Independent Shelf for Omarchy GTK4 interface."""
import hashlib
import ipaddress
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango
from shelf_core import Store, image_thumbnail
from shelf_capture import Monitor
from shelf_clipboard import active_window, safe_target, copy_item, paste_to


def item_kind(item):
    """Classify locally; links are syntax-checked, never fetched or resolved."""
    if item['mime'] == 'text/uri-list':
        return 'Files'
    if item['mime'].startswith('image/'):
        return 'Images'
    text = item['label']
    try:
        uri = urlsplit(text)
        if (uri.scheme not in ('http', 'https') or not uri.hostname or
                any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c in '\\<>"{}|^`' for c in text) or
                re.search(r'%(?![0-9A-Fa-f]{2})', text) or
                uri.port == 0 or uri.username or uri.password):
            return 'Text'
        host = uri.hostname.encode('idna').decode('ascii').rstrip('.')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part) for part in host.split('.')):
                return 'Text'
        return 'Links'
    except (ValueError, UnicodeError):
        return 'Text'


CSS = b'''
window { background: #202122; color: #f2f2f0; font-family: sans-serif; }
.title { font-size: 21px; font-weight: 700; }
.muted, .status { color: #c2c4c5; font-size: 12px; }
.kind { color: #dedfdd; font-size: 12px; font-weight: 600; }
searchentry { background: #2c2e30; border: 1px solid #55585b; border-radius: 8px; padding: 5px; }
button { background: #303234; color: #f2f2f0; border: 1px solid #525557; border-radius: 8px; padding: 6px 10px; }
button:hover { background: #414446; }
button:focus-visible { outline: 2px solid #b5d9ca; outline-offset: 2px; }
button:disabled, button.primary:disabled, button.danger:disabled { background: #292b2d; color: #909496; border-color: #414446; }
button.primary, button.active-filter { background: #b5d9ca; color: #192822; border-color: #b5d9ca; }
button.danger { color: #ffb7b7; }
button.card { background: #343638; border: 2px solid #505355; padding: 14px; border-radius: 10px; }
button.card.selected { background: #3b403e; border-color: #b5d9ca; }
.card-title { font-size: 15px; }
.preview { background: #303234; padding: 16px; }
textview, textview text { background: #303234; color: #f2f2f0; font-family: monospace; font-size: 14px; }
.empty { color: #c2c4c5; font-size: 15px; padding: 20px; }
.capture-state { color: #f3d4a4; font-size: 12px; font-weight: 700; }
'''


def label(text, css=None, xalign=0):
    obj = Gtk.Label(label=text, xalign=xalign)
    if css:
        obj.add_css_class(css)
    return obj


def button(text, callback, css=None):
    obj = Gtk.Button(label=text)
    if css:
        obj.add_css_class(css)
    obj.connect('clicked', lambda *_: callback())
    return obj


class ShelfApp(Gtk.Application):
    def __init__(self, directory, paused=False):
        self.directory = Path(directory).expanduser().resolve()
        digest = hashlib.sha256(str(self.directory).encode()).hexdigest()[:20]
        super().__init__(application_id='org.nous.shelf.h' + digest, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.paused = paused
        self.window = None
        self.store = None
        self.monitor = Monitor(self.directory)
        self.selected = None
        self.target = None
        self.timer = None
        self.version = None
        self.visible_count = 0
        self.closed = False
        self.preview_window = None
        self.connect('shutdown', lambda *_: self.shutdown_cleanly())

    def do_activate(self):
        target = active_window()
        if target and not str(target.get('class', '')).startswith('org.nous.shelf'):
            self.target = target
        if self.window is None:
            self.store = Store(self.directory)
            self.build_window()
            self.hold()
            self.timer = GLib.timeout_add(700, self.tick)
            if not self.paused:
                self.set_capture(True)
        self.update_target()
        self.refresh()
        self.window.present()
        if self.selected in self.card_widgets:
            self.card_widgets[self.selected].grab_focus()

    def build_window(self):
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS.decode('utf-8'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.ApplicationWindow(application=self, title='Shelf for Omarchy')
        self.window.set_default_size(1080, 400)
        self.window.set_size_request(700, 380)
        self.window.connect('close-request', lambda *_: self.hide_window())
        self.window.set_decorated(False)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, 'set_margin_' + side)(12)
        self.window.set_child(root)
        top = Gtk.Box(spacing=10)
        top.append(label('Shelf', 'title'))
        self.capture_state = label('Capture paused', 'capture-state')
        self.capture_state.set_hexpand(True)
        top.append(self.capture_state)
        self.search = Gtk.SearchEntry(placeholder_text='Search shelf…')
        self.search.set_size_request(200, -1)
        self.search.connect('search-changed', lambda *_: self.refresh())
        top.append(self.search)
        self.pause_button = button('Resume capture', lambda: self.set_capture(self.paused))
        top.append(self.pause_button)
        menu = Gtk.MenuButton(icon_name='open-menu-symbolic', tooltip_text='More options')
        popover = Gtk.Popover()
        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        options.append(button('Clear unpinned', self.confirm_clear, 'danger'))
        options.append(button('Quit', self.quit))
        popover.set_child(options)
        menu.set_popover(popover)
        top.append(menu)
        top.append(button('Hide', self.hide_window))
        root.append(top)
        filters = Gtk.Box(spacing=6)
        self.filter_name = 'All'
        self.filter_buttons = {}
        for name in ('All', 'Pinned', 'Text', 'Images', 'Links', 'Files'):
            obj = button(name, lambda name=name: self.set_filter(name))
            self.filter_buttons[name] = obj
            filters.append(obj)
        self.count_label = label('', 'muted')
        self.count_label.set_hexpand(True)
        self.count_label.set_xalign(1)
        filters.append(self.count_label)
        root.append(filters)
        self.cards = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.card_widgets = {}
        self.scroll = Gtk.ScrolledWindow(vexpand=True)
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.scroll.set_child(self.cards)
        root.append(self.scroll)
        self.empty = label('Your shelf is empty. Resume capture when ready.', 'empty', 0.5)
        self.empty.set_vexpand(True)
        root.append(self.empty)
        actions = Gtk.Box(spacing=6)
        self.pin_button = button('Pin', self.toggle_pin)
        self.delete_button = button('Delete', self.delete_selected, 'danger')
        self.copy_button = button('Copy', self.copy_selected)
        self.paste_button = button('Paste back ↗', self.paste_selected, 'primary')
        for obj in (self.pin_button, self.delete_button, self.copy_button, self.paste_button):
            actions.append(obj)
        self.target_label = label('Paste target: none', 'muted')
        self.target_label.set_hexpand(True)
        self.target_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.target_label.set_max_width_chars(45)
        actions.append(self.target_label)
        root.append(actions)
        self.status = label('Paused • Nothing is being captured.', 'status')
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        root.append(self.status)
        root.append(label('← → Browse   ·   Enter Copy   ·   Space Preview   ·   Ctrl+F Search   ·   Esc Hide', 'muted'))
        # Preview is populated on demand, not a permanent split pane.
        self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.detail_title = label('', 'card-title')
        for name, callback, accelerators in [('quit', self.quit, ['<Control>q']), ('hide', self.hide_window, []), ('copy', self.copy_selected, ['<Control><Shift>c'])]:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda a, p, cb=callback: cb())
            self.add_action(action)
            self.set_accels_for_action('app.' + name, accelerators)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.handle_key)
        self.window.add_controller(keys)
        self.preview_button = button('Preview', self.open_preview)
        actions.insert_child_after(self.preview_button, self.delete_button)
        self.show_selected()

    def handle_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            return self.hide_window()
        if state & Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        focus = self.window.get_focus()
        while focus:
            if isinstance(focus, (Gtk.Editable, Gtk.TextView, Gtk.SearchEntry)):
                return False
            focus = focus.get_parent()
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK):
            return False
        # Keep native button/menu activation outside the card strip.
        focus = self.window.get_focus()
        if focus and focus not in self.card_widgets.values():
            return False
        ids = list(self.card_widgets)
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down) and ids:
            index = ids.index(self.selected) if self.selected in ids else 0
            index = max(0, min(len(ids) - 1, index + (1 if keyval in (Gdk.KEY_Right, Gdk.KEY_Down) else -1)))
            self.select(ids[index])
            self.card_widgets[ids[index]].grab_focus()
            adjustment = self.scroll.get_hadjustment()
            card = self.card_widgets[ids[index]]
            x = card.get_allocation().x
            adjustment.clamp_page(x, x + card.get_width())
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and ids:
            self.copy_selected()
            return True
        if keyval == Gdk.KEY_space and ids:
            self.open_preview()
            return True
        return False

    def open_preview(self):
        if self.selected is None:
            return
        if self.preview_window:
            self.preview_window.present()
            return
        self.preview_window = Gtk.Window(application=self, title='Shelf preview', transient_for=self.window, modal=True)
        self.preview_window.set_default_size(640, 440)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class('preview')
        self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, vexpand=True)
        self.detail_title = label('', 'card-title')
        box.append(self.detail_title)
        box.append(self.preview)
        box.append(button('Close preview', self.close_preview))
        self.preview_window.set_child(box)
        self.preview_window.connect('close-request', lambda *_: self.close_preview())
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', lambda c, k, code, state: self.close_preview() if k == Gdk.KEY_Escape else False)
        self.preview_window.add_controller(keys)
        self.show_selected()
        self.preview_window.present()

    def close_preview(self):
        if self.preview_window:
            window = self.preview_window
            self.preview_window = None
            window.destroy()
        return True

    def notify(self, message):
        self.status.set_text(message)
        self.capture_state.set_text('Capture paused' if self.paused else 'Capture on')

    def set_capture(self, enabled):
        try:
            if enabled:
                self.monitor.start()
            else:
                self.monitor.stop()
            self.paused = not enabled
            self.pause_button.set_label('Resume capture' if self.paused else 'Pause capture')
            self.notify('Paused • Nothing is being captured.' if self.paused else 'Capturing • Text, images and local file references stay on this device.')
        except OSError:
            self.paused = True
            self.pause_button.set_label('Resume capture')
            self.notify('Capture could not start. Check that wl-paste is installed and Wayland is running.')

    def tick(self):
        if self.closed:
            return False
        if not self.paused and not self.monitor.running:
            self.paused = True
            self.pause_button.set_label('Resume capture')
            self.notify('Capture stopped unexpectedly. Your compositor must support wl-paste --watch.')
        target = active_window()
        if target and not str(target.get('class', '')).startswith('org.nous.shelf'):
            self.target = target
            self.update_target()
        version = self.store.db.execute('PRAGMA data_version').fetchone()[0]
        if self.version != version:
            self.version = version
            self.refresh()
        return True

    def update_target(self):
        if not self.window:
            return
        if safe_target(self.target):
            self.target_label.set_text('Paste target: ' + str(self.target.get('title') or self.target['class'])[:100])
        else:
            self.target_label.set_text('Paste back unavailable: no safe previous window. Use Copy and paste manually.')
        self.paste_button.set_sensitive(self.selected is not None and safe_target(self.target))

    def set_filter(self, name):
        if name not in ('All', 'Pinned', 'Text', 'Images', 'Links', 'Files'):
            raise ValueError('Unknown filter')
        self.close_preview()
        self.filter_name = name
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        selected = self.selected
        had_card_focus = self.window.get_focus() in self.card_widgets.values()
        child = self.cards.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.cards.remove(child)
            child = nxt
        name = self.filter_name
        items = [item for item in self.store.items(self.search.get_text())
                 if name == 'All' or (name == 'Pinned' and item['pinned'])
                 or (name == 'Text' and item['mime'] == 'text/plain')
                 or (name not in ('Pinned', 'Text') and item_kind(item) == name)]
        self.visible_count = len(items)
        self.count_label.set_text(f'{len(items)} items')
        self.empty.set_visible(not items)
        self.empty.set_text('No matches. Try another filter or search.' if name != 'All' or self.search.get_text() else 'Your shelf is empty. Resume capture when ready.')
        self.scroll.set_visible(bool(items))
        self.card_widgets = {}
        for key, obj in self.filter_buttons.items():
            (obj.add_css_class if key == name else obj.remove_css_class)('active-filter')
        for item in items:
            ident = item['id']
            card = button(None, lambda ident=ident: self.select(ident), 'card')
            card.set_size_request(224, 204)
            gesture = Gtk.GestureClick()
            gesture.set_button(1)
            gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            gesture.connect('pressed', lambda g, count, x, y, ident=ident: self.card_pressed(ident, count))
            card.add_controller(gesture)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            content.append(label(('★ Pinned · ' if item['pinned'] else '') + item_kind(item), 'kind'))
            if item['mime'].startswith('image/'):
                try:
                    pixbuf, _ = image_thumbnail(item['data'])
                    preview = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                    preview.set_content_fit(Gtk.ContentFit.CONTAIN)
                    preview.set_can_shrink(True)
                except ValueError:
                    preview = label('Image preview unavailable', 'muted')
            else:
                preview = label(item['label'][:600], 'card-title')
                preview.set_wrap(True)
                preview.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                preview.set_lines(5)
                preview.set_ellipsize(Pango.EllipsizeMode.END)
                preview.set_max_width_chars(22)
                preview.set_yalign(0)
            preview.set_vexpand(True)
            content.append(preview)
            timestamp = time.strftime('%d %b · %H:%M', time.localtime(item['touched'] / 1e9))
            content.append(label(f'{timestamp} · {len(item["data"]):,} B', 'muted'))
            card.set_child(content)
            accessible_name = f'{item_kind(item)} card: {item["label"][:80]}'
            card.update_property([Gtk.AccessibleProperty.LABEL], [accessible_name])
            self.cards.append(card)
            self.card_widgets[ident] = card
        self.select(selected if selected in self.card_widgets else next(iter(self.card_widgets), None))
        if had_card_focus and self.selected in self.card_widgets:
            self.card_widgets[self.selected].grab_focus()

    def card_pressed(self, ident, count):
        self.select(ident)
        if count == 2:
            self.copy_selected()

    def select(self, ident):
        if ident is not None and ident not in self.card_widgets:
            return
        if ident != self.selected:
            self.close_preview()
        self.selected = ident
        for key, obj in self.card_widgets.items():
            (obj.add_css_class if key == ident else obj.remove_css_class)('selected')
        self.show_selected()

    def show_selected(self):
        child = self.preview.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.preview.remove(child)
            child = nxt
        item = self.store.get(self.selected) if self.selected is not None else None
        for obj in (self.pin_button, self.delete_button, self.copy_button, self.preview_button):
            obj.set_sensitive(item is not None)
        self.update_target()
        self.pin_button.set_label('Unpin' if item and item['pinned'] else 'Pin')
        if not self.preview_window:
            return
        if not item:
            self.detail_title.set_text('A little space for everything.')
            empty = label('Text. Images. Files.\n\nSelect an item to preview it, pin it,\nor send it back to your last window.', 'muted', 0.5)
            empty.set_wrap(True)
            empty.set_vexpand(True)
            self.preview.append(empty)
            return
        self.pin_button.set_label('Unpin' if item['pinned'] else 'Pin')
        self.detail_title.set_text('Image preview' if item['mime'].startswith('image/') else ('File references' if item['mime'] == 'text/uri-list' else 'Text preview'))
        if item['mime'].startswith('image/'):
            try:
                pixbuf, _ = image_thumbnail(item['data'])
                pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                pic.set_vexpand(True)
                self.preview.append(pic)
            except ValueError:
                self.preview.append(label('Image preview unavailable'))
        else:
            text = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            text.get_buffer().set_text(item['label'][:60000])
            scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
            scroll.set_child(text)
            self.preview.append(scroll)
            if len(item['label']) > 60000:
                self.preview.append(label('Preview truncated. Copy preserves the full item.', 'muted'))
            if item['mime'] == 'text/uri-list':
                self.preview.append(label('References only • files are not copied into Shelf.', 'muted'))

    def toggle_pin(self):
        if self.selected is not None:
            item = self.store.get(self.selected)
            self.store.pin(self.selected, not item['pinned'])
            self.refresh()

    def delete_selected(self):
        self.close_preview()
        if self.selected is not None:
            self.store.delete(self.selected)
            self.selected = None
            self.refresh()
            self.notify('Item deleted from Shelf. The system clipboard is unchanged.')

    def confirm_clear(self):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.NONE, text='Clear all unpinned items?',
                                   secondary_text='Pinned items will stay. This cannot be undone. The system clipboard is unchanged.')
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Clear unpinned', Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        def response(obj, answer):
            if answer == Gtk.ResponseType.ACCEPT:
                self.store.clear_unpinned()
                self.refresh()
                self.notify('Unpinned history cleared.')
            obj.destroy()
        dialog.connect('response', response)
        dialog.present()

    def copy_selected(self):
        if self.selected is not None:
            try:
                copy_item(self.store.get(self.selected))
                self.notify('Copied. Paste wherever you need it.')
            except (ValueError, OSError) as exc:
                self.notify(str(exc))

    def paste_selected(self):
        if self.selected is not None:
            try:
                if not safe_target(self.target):
                    raise ValueError('No safe paste target. Use Copy instead.')
                target = dict(self.target)
                copy_item(self.store.get(self.selected))
                paste_to(target)
                self.notify('Paste shortcut sent to ' + str(target.get('title', target['class']))[:100])
            except (ValueError, OSError) as exc:
                self.window.present()
                self.notify(str(exc))

    def hide_window(self):
        self.close_preview()
        self.window.set_visible(False)
        return True

    def shutdown_cleanly(self):
        if self.closed:
            return
        self.closed = True
        self.close_preview()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        self.monitor.stop()
        if self.store:
            self.store.close()
            self.store = None
