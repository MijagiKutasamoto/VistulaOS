## VistulaOS Installer (Python/GTK)

GUI instalator dla VistulaOS w Pythonie (GTK3 / PyGObject) z kreatorem krok-po-kroku, logowaniem oraz podstawowym multilanguage (PL/EN).

Aktualnie:
- przełączanie języka działa od razu (rebuild UI)
- jest strona konfiguracji sieci (NetworkManager + opcjonalny profil Wi‑Fi)
- jest strona sterowników i pakietów (profile: gracze/twórcy/księgowi/programiści; instalacja tylko jeśli w systemie docelowym jest `pacman`)

### Uruchomienie

W trybie bezpiecznym (bez zmian na dysku):

`python -m vistula_installer --dry-run`

W trybie instalacji (wymaga uprawnień root):

`sudo python -m vistula_installer`

### Zależności (typowo w live ISO)

- `python3-gi`, `gir1.2-gtk-3.0`
- `lsblk`, `parted`, `wipefs`, `mkfs.vfat`, `mkfs.ext4`
- `rsync`
- `grub-install`, `update-grub`

Logi zapisują się domyślnie do `~/.local/state/vistula-installer/installer.log`.

