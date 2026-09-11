"""Dispatcher protocol regressions; subprocess seam avoids real keystrokes."""
import json
import unittest
from unittest.mock import patch
from shelf_clipboard import paste_to

TARGET = {'address': '0xabc', 'pid': 100, 'class': 'SyntheticEditor'}
LUA = ['hyprctl', 'dispatch', 'hl.dsp.focus({ window = "address:0xabc" })']
LEGACY = ['hyprctl', 'dispatch', 'focuswindow', 'address:0xabc']

class HyprlandTests(unittest.TestCase):
    def run_paste(self, status, expected):
        calls = []
        def run(args, *unused, **kwargs):
            calls.append(args)
            if args == ['hyprctl', '-j', 'clients']:
                return json.dumps([TARGET]).encode()
            if args == ['hyprctl', '-j', 'status']:
                if isinstance(status, Exception):
                    raise status
                return status
            if args == ['hyprctl', '-j', 'activewindow']:
                return json.dumps(TARGET if expected in calls else {}).encode()
            return b'ok'
        with patch('shelf_clipboard.read_limited', run), patch('shelf_clipboard.time.sleep'):
            paste_to(TARGET)
        self.assertIn(expected, calls)
        self.assertEqual(calls[-1][0], 'wtype')

    def test_lua_provider_focuses_using_current_dispatcher(self):
        self.run_paste(b'{"configProvider":"lua"}', LUA)

    def test_legacy_and_pre_status_releases_keep_legacy_syntax(self):
        for status in (b'{"configProvider":"hyprlang"}', b'unknown request', ValueError('unsupported'), b'null'):
            with self.subTest(status=status):
                self.run_paste(status, LEGACY)

    def test_dispatch_error_never_sends_keys_even_if_target_already_focused(self):
        calls = []
        def run(args, *unused, **kwargs):
            calls.append(args)
            if args[-1] == 'clients':
                return json.dumps([TARGET]).encode()
            if args[-1] == 'status':
                return b'{"configProvider":"lua"}'
            if args[-1] == 'activewindow':
                return json.dumps(TARGET).encode()
            return b'error: dispatcher rejected'
        with patch('shelf_clipboard.read_limited', run), patch('shelf_clipboard.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'focus'):
                paste_to(TARGET)
        self.assertFalse(any(c[0] == 'wtype' for c in calls))

    def test_changed_identity_or_unverified_focus_never_sends_keys(self):
        for phase in ('clients', 'activewindow'):
            for key, value in (('address', '0xdef'), ('pid', 999), ('class', 'OtherEditor')):
                with self.subTest(phase=phase, key=key):
                    calls = []
                    def run(args, *unused, **kwargs):
                        calls.append(args)
                        changed = dict(TARGET, **{key: value})
                        if args[-1] == 'clients':
                            return json.dumps([changed if phase == 'clients' else TARGET]).encode()
                        if args[-1] == 'activewindow':
                            return json.dumps(changed).encode()
                        if args[-1] == 'status':
                            return b'{"configProvider":"lua"}'
                        return b'ok'
                    with patch('shelf_clipboard.read_limited', run), patch('shelf_clipboard.time.sleep'):
                        with self.assertRaises(ValueError):
                            paste_to(TARGET)
                    self.assertFalse(any(c[0] == 'wtype' for c in calls))
