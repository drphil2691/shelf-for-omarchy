# Shelf for Omarchy

An independent GTK4 clipboard-history app for Linux/Wayland, tested on Omarchy with Hyprland. **Not Nate Jones’s Mac Shelf app, not a port of its source, and not affiliated with Nate Jones or the Omarchy project.** No original DMG code or graphics are distributed. The SVG icon is original artwork for this project.

## Requirements

- Linux, Python 3.10+ with system PyGObject (`gi`), GTK 4.12+ and GdkPixbuf.
- Wayland compositor with the wlroots data-control protocol, session D-Bus.
- `wl-copy` and `wl-paste` (usually the `wl-clipboard` package).
- Hyprland, `hyprctl` and `wtype` for Paste back; this feature is Hyprland-specific.
- `desktop-file-validate` (usually `desktop-file-utils`) for installer tests.

Dependencies are **not bundled or installed**. Install them using your distribution's package manager. Tested on Arch Linux/Omarchy with Hyprland; other Linux desktops/distributions are not certified. No macOS, Windows, X11 or GNOME Wayland compatibility is claimed. No pip dependencies, accounts, API keys, or network services are needed. Use a Python interpreter able to import your system GTK bindings (`/usr/bin/python` on Arch, commonly `/usr/bin/python3` elsewhere).

## Install and launch

Quit any running Shelf instance first. From this checkout, on Arch/Omarchy:

```sh
/usr/bin/python install.py
```

On distributions naming system Python `python3`, use that instead. The installer records the chosen interpreter in the launcher. Search your application menu for **Shelf**. The menu entry launches with **`--paused`**, without a terminal, reading or watching the clipboard. Click **Resume capture** explicitly when ready; resuming can capture the currently held clipboard.

User-only destinations (or beneath `$XDG_DATA_HOME` when set to an absolute path):

- `~/.local/share/shelf-for-omarchy-app/`: runtime and original icon
- `~/.local/share/applications/shelf-for-omarchy.desktop`: menu entry
- `~/.local/share/shelf-for-omarchy/`: separate private history, never copied/removed by the installer

No sudo, autostart, service, hotkey, global configuration, or desktop rule is installed. Existing app/entry targets are renamed to `.backup-<timestamp>` before replacement. Quit first before upgrading. Backups remain for manual rollback; preserve the current installed targets before restoring a matching app and desktop-entry backup. Menu caching may delay discovery until the launcher refreshes.

For an uninstalled checkout, use your system Python:

```sh
/usr/bin/python shelf --paused
```

**Running `shelf` without `--paused` starts capture immediately.** The executable shebang uses Arch's `/usr/bin/python`; invoking through your system Python works on other distributions. `--paused` is only a startup option: reopening an already-running active instance does not pause it. Closing/hiding the window does not quit or stop capture. Use **More options → Quit** or **Ctrl+Q** to exit normally. There is no tray icon.

## Using your shelf

- **Text:** UTF-8 text, including multiline and Unicode content.
- **Images:** PNG, JPEG and WebP, with aspect-preserving image thumbnails. The original bytes are retained for copying; the preview is deliberately low-resolution.
- **Files:** local `text/uri-list` references, with file icons and decoded path previews. Shelf does not open the referenced files, copy their contents into its database, or fetch remote URLs. Moving/deleting the source file breaks its reference. File-manager cut/move flags are not retained: this is a copy shelf, not a file mover.
- **Compact cards:** the main window requests 1080 × 400 logical pixels, with a horizontally scrolling card strip and a selected border. It remains usable at 760 × 400. Scroll horizontally with a trackpad or scrollbar; arrow keys keep the selected card in view. Your compositor can override size hints or tile the window. Use your existing floating/move/resize controls if desired; Shelf does not install window rules.
- **Filters:** All, Pinned, Text, Images, Links and Files combine with search. Text includes links. Links are derived only from whole-text, syntactically valid HTTP/HTTPS URLs (no whitespace, credentials, invalid hostname/port or malformed percent escapes). Classification performs no DNS lookup, fetch, website preview or automatic navigation. A syntactically valid URL need not exist.
- **Search:** Ctrl+F focuses case-insensitive literal matching on text, decoded file paths and image metadata. Spaces, arrows and Enter retain their normal editing behavior there. No OCR or image-content search.
- **Preview:** Space on a card, or the selected item's Preview button, opens an on-demand expanded view. Close preview / Escape closes only the preview. Text can be selected and copied with the native text control; the preview is not an editor. Images remain deliberately low-resolution. Card snippets are truncated; Copy preserves the full original payload.
- **Metadata:** type, pin state, last captured time and payload byte size only. No source app, employer, website attribution, or other provenance is invented.
- **Pin / Unpin:** pins stay at the top and survive pruning and Clear unpinned.
- **Delete:** removes the selected history item. **More options (☰) → Clear unpinned** asks for confirmation; Cancel is the default. Neither operation changes the system clipboard.
- **Copy:** copies the selected item. Arrow keys browse while a card has focus; Enter, double-clicking a card, or Ctrl+Shift+C copies. Opening/reopening Shelf focuses its selected card. Tab moves through native controls; their Enter/Space behavior remains native.
- **Paste back:** copies the item and sends Ctrl+V to the displayed previous Hyprland window. Its exact address, process ID and class must still match; focus is checked before the shortcut is sent. There is no arbitrary fallback window. Recognised terminal windows are blocked; use Copy and paste manually there. The destination app must support Ctrl+V and the selected format. A successful shortcut is not proof that the destination accepted its content.
- **Hide / Escape:** hides the window. Launch again with the same data directory to reopen. **Quit / Ctrl+Q:** stops capture and exits.

Each data directory has one GTK application instance. A second launch reopens that instance; `--paused` is a startup setting, not a command to pause an already running instance. Separate test data directories get separate instances.

## Storage and limits

Default data directory:

```text
$XDG_DATA_HOME/shelf-for-omarchy/
```

If XDG_DATA_HOME is unset, this means `~/.local/share/shelf-for-omarchy/`. History lives in `history.sqlite3`; SQLite may temporarily create journal files. The directory is mode 0700, the database 0600, and the launcher sets umask 077. Database symlinks are refused. This is a dedicated application directory; do not point `--data-dir` at an unrelated directory.

**History is plaintext, not encrypted.** Anyone with access to your Unix account, backups, root privileges, or an unlocked disk can read it. Deletion is not a secure disk erase; database free pages, filesystem snapshots and backups may retain data. Restrictive file permissions are not encryption.

Limits: 10 MiB per item, 24 megapixels per decoded image, 200 unpinned items and 100 MiB of unpinned payload. Oldest unpinned items are pruned first. **Pinned items are retained outside the history count/aggregate byte limits**, so pinning indefinitely grows storage. The database can exceed the payload budget because of labels, indexes, pinned items and SQLite allocation. Empty, invalid, unsupported or oversized clipboard items are skipped. Exact MIME+byte duplicates update the existing entry without losing its pin.

## Privacy and limitations

- **No network access, telemetry, cloud sync or content logging.** Clipboard helpers are local subprocesses invoked with argument arrays, never shell interpolation. File URIs are stored as references and never executed.
- The capture helper drops `CLIPBOARD_STATE=sensitive`, `nil`, `clear`, unknown or absent states. It also ignores clipboard offers containing password/sensitive/secret MIME hints, including `x-kde-passwordManagerHint`.
- **These are best-effort hints, not a password detector.** Some applications/password managers do not mark secrets. Rapid clipboard changes between a watch notification, MIME inspection and reading can race; the currently offered preferred format may differ from the original event. Pause before copying passwords, recovery codes, tokens, financial details or other sensitive data. Shelf cannot guarantee that such content will never enter history.
- The watcher stops on normal Quit/termination and is tied to the app's lifetime with a Linux parent-death signal. A clipboard callback already underway during a crash may finish briefly; no permanent daemon is installed.
- Only the ordinary clipboard is captured, not the primary selection. Rich HTML/RTF, arbitrary binary formats and remote file URIs are unsupported. When several representations are offered, local file URIs take priority, then supported images, then plain text. Some source applications cannot offer their clipboard after they exit.
- Paste back is Hyprland-specific. It detects the running config provider with `hyprctl -j status`: Lua uses `hl.dsp.focus({ window = "address:…" })`; legacy providers and older releases without `status` use `focuswindow address:…`. Dispatch must return `ok`, and the destination identity and actual focus are independently checked before Ctrl+V. Known terminals are blocked conservatively, but an embedded shell or renamed terminal cannot be reliably identified. Check the displayed target before using Paste back. A last-moment focus change remains possible between focus verification and the compositor receiving the shortcut. Use Copy for destinations where an accidental paste could be harmful.
- A large pinned collection can make the card strip slower. Capture subprocesses use bounded reads and timeouts; invalid captures are intentionally not logged with their content.
- Other clipboard managers may also record clipboard data independently. Pausing or deleting from Shelf does not control them.

## Tests

```sh
/usr/bin/python -m unittest discover -s tests -v
```

Tests use temporary stores and synthetic fixtures. GTK tests require a graphical session and open short-lived paused windows; they do not start the real clipboard watcher. Installer tests use disposable homes, validate desktop syntax and verify history preservation and upgrade/uninstall behavior. Some current GTK/PyGObject/Python combinations emit upstream deprecation warnings. Full screen-reader behavior is not certified.

## Uninstall

Quit Shelf first, including any separate test instances. With the same `XDG_DATA_HOME` used to install:

```sh
/usr/bin/python ~/.local/share/shelf-for-omarchy-app/install.py --uninstall
# Or, from the source checkout:
/usr/bin/python install.py --uninstall
```

Use your system Python name as appropriate. With custom XDG_DATA_HOME, the installed script is beneath that directory instead. This removes only the installed runtime and desktop entry. **History, upgrade backups and source checkout are retained.** No automatic history deletion is provided. Remove unwanted backup directories manually only after checking their contents. The installer does not stop a running process: quit before uninstalling.

## Contributing and licence

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the [MIT License](LICENSE).
