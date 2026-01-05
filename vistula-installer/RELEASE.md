# Vistula Installer 1.0.0

## Build

### Source run

- `python -m vistula_installer --dry-run`

### PyInstaller (single binary)

- Install pyinstaller (example): `python -m pip install --user pyinstaller`
- Build: `./scripts/build_linux_pyinstaller.sh`
- Output: `dist/vistula-installer`

## Notes

- GTK (PyGObject) is usually provided by the system (not pip):
  - Debian/Ubuntu: `sudo apt install python3-gi gir1.2-gtk-3.0`
  - Arch: `sudo pacman -S python-gobject gtk3`

- Assets:
  - i18n JSON files are bundled in PyInstaller build.
  - In dev mode, assets are read from the repo.
