# Vistula Terminal (Python)

Lekki terminal dla VistulaOS oparty o **GTK3 + VTE** (PyGObject). Korzysta z motywów Cinnamon/GTK (kolory okna i font z ustawień) i ma tryb wpisywania hasła maskowany `*` z możliwością cofania.

## Zależności (Debian/Ubuntu/Mint)

- `python3`
- `python3-gi`
- `gir1.2-gtk-3.0`
- `gir1.2-vte-2.91`

Przykład instalacji:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91
```

## Zależności (Arch Linux)

Pakiety:

- `python`
- `python-gobject`
- `gtk3`
- `vte3`

Instalacja:

```bash
sudo pacman -S --needed python python-gobject gtk3 vte3
```

Szybki test, czy PyGObject/VTE działa:

```bash
python -c "import gi; gi.require_version('Vte','2.91'); from gi.repository import Vte; print('OK')"
```

## Uruchomienie

Z katalogu projektu:

```bash
python3 src/vistula_terminal.py
```

### VS Code (Flatpak)

Jeśli używasz VS Code z Flatpaka, środowisko może ładować moduł `gi` z `/app/...` (bez `require_version`). Wtedy uruchamiaj aplikację na hoście:

```bash
flatpak-spawn --host python /pełna/ścieżka/do/Vistula-Terminal/src/vistula_terminal.py
```

Uruchomienie konkretnej komendy (zamiast powłoki):

```bash
python3 src/vistula_terminal.py bash -lc 'echo hello; exec bash'
```

## Skróty

- `Ctrl+Shift+C` kopiuj
- `Ctrl+Shift+V` wklej

## Mysz

- Prawy klik: menu kontekstowe (Kopiuj/Wklej)
- Środkowy klik: wklej z PRIMARY (typowe linuksowe wklejanie zaznaczenia)

## Multi-lang

Aplikacja dobiera język automatycznie z `LANG` / `LC_ALL` / `LC_MESSAGES`.

Wymuszenie języka:

```bash
VISTULA_LANG=pl python3 src/vistula_terminal.py
```

Tłumaczenia są w:

- [data/i18n/en.json](data/i18n/en.json)
- [data/i18n/pl.json](data/i18n/pl.json)

## Ikona

Domyślna nazwa ikony: `org.vistula.Terminal`.

Do projektu dodana jest ikona SVG:

- [data/icons/hicolor/scalable/apps/org.vistula.Terminal.svg](data/icons/hicolor/scalable/apps/org.vistula.Terminal.svg)

Przy uruchamianiu „niezainstalowanym” aplikacja dodaje `data/icons` do ścieżki wyszukiwania ikon i używa tej ikony.

## Hasła (maskowanie `*`)

Aplikacja wykrywa popularne prompt’y haseł (np. `Password:` / `Hasło:` / `Passphrase:`) i wtedy pokazuje na dole pole "Hasło:" z maskowaniem `*`.

- Backspace działa normalnie (można cofnąć, gdy się pomylisz).
- `Esc` anuluje tryb hasła (nie wysyła nic do procesu).

To jest heurystyka (działa dla typowych promptów). Jeśli chcesz inną listę słów-kluczy lub zachowanie dla konkretnej komendy, dopasuję regex.
