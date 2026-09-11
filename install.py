#!/usr/bin/env python3
"""User-only desktop installation. Never installs or removes clipboard history."""
import os
from pathlib import Path
import shutil
import sys
import time

SOURCE = Path(__file__).resolve().parent
RUNTIME_FILES = ('shelf', 'shelf_core.py', 'shelf_capture.py', 'shelf_clipboard.py',
                 'shelf_ui.py', 'assets/shelf-for-omarchy.svg', 'install.py')


def desktop_string(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def exec_argument(value):
    value = str(value).replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return desktop_string('"' + value + '"')


def locations():
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    if not data.is_absolute():
        raise ValueError('XDG_DATA_HOME must be absolute')
    return data / 'shelf-for-omarchy-app', data / 'applications/shelf-for-omarchy.desktop'


def install():
    runtime, entry = locations()
    if runtime.resolve() == SOURCE:
        raise ValueError('Run installation from the source checkout, not the installed copy')
    for name in RUNTIME_FILES:
        if not (SOURCE / name).is_file():
            raise ValueError('Missing source file: ' + name)
    interpreter = str(Path(sys.executable).absolute())
    stamp = str(time.time_ns())
    for target in (runtime, entry):
        if target.exists() or target.is_symlink():
            backup = target.with_name(target.name + '.backup-' + stamp)
            target.rename(backup)
            print('Backup:', backup)
    runtime.mkdir(parents=True)
    for name in RUNTIME_FILES:
        target = runtime / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / name, target)
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text('\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Shelf for Omarchy',
        'Comment=Local clipboard history; starts paused',
        'Exec=' + exec_argument(interpreter) + ' ' + exec_argument(runtime / 'shelf') + ' --paused',
        'Icon=' + desktop_string(runtime / 'assets/shelf-for-omarchy.svg'),
        'Terminal=false', 'Categories=Utility;', 'Keywords=Shelf;Clipboard;History;',
        'StartupNotify=true', '',
    ]))
    print('Installed:', runtime)
    print('Desktop entry:', entry)
    print('History untouched. Search your application menu for Shelf.')


def uninstall():
    runtime, entry = locations()
    if entry.exists() or entry.is_symlink():
        entry.unlink()
    if runtime.is_symlink():
        runtime.unlink()
    elif runtime.exists():
        shutil.rmtree(runtime)
    print('Removed app and desktop entry. History and upgrade backups retained.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true', help='remove only installed app and menu entry; quit Shelf first')
    args = parser.parse_args()
    try:
        uninstall() if args.uninstall else install()
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
