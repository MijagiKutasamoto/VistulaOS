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

## Uruchomienie

Z katalogu projektu:

```bash
python3 src/vistula_terminal.py
```

Uruchomienie konkretnej komendy (zamiast powłoki):

```bash
python3 src/vistula_terminal.py bash -lc 'echo hello; exec bash'
```

## Skróty

- `Ctrl+Shift+C` kopiuj
- `Ctrl+Shift+V` wklej

## Hasła (maskowanie `*`)

Aplikacja wykrywa popularne prompt’y haseł (np. `Password:` / `Hasło:` / `Passphrase:`) i wtedy pokazuje na dole pole "Hasło:" z maskowaniem `*`.

- Backspace działa normalnie (można cofnąć, gdy się pomylisz).
- `Esc` anuluje tryb hasła (nie wysyła nic do procesu).

To jest heurystyka (działa dla typowych promptów). Jeśli chcesz inną listę słów-kluczy lub zachowanie dla konkretnej komendy, dopasuję regex.
