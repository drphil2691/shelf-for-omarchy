# Contributing

Small, tested improvements are welcome. Discuss substantial changes before implementation.

1. Use system Python with GTK4/PyGObject available; see README requirements.
2. Write a regression test before changing behavior. Use temporary stores and synthetic clipboard fixtures only.
3. Run `python -m unittest discover -s tests -v` in a graphical Wayland session. Never run live clipboard tests on private content.
4. Check installation in a disposable HOME/XDG_DATA_HOME. Validate generated entries with `desktop-file-validate`.
5. Explain behavior changes, privacy implications, test results and known limitations in your contribution.

Do not commit history databases, clipboard contents, logs, raw screenshots, local evidence, personal paths, credentials, binaries or third-party app assets. Do not add network requests, telemetry, autostart or global hotkeys without explicit design discussion. Screenshots, if contributed, must show only synthetic content with no host paths or unrelated windows.

Keep the project independent; do not imply official affiliation with Nate Jones or Omarchy. Contributions are provided under the project's MIT License.
