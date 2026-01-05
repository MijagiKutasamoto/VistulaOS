# Vistula-updater (MVP)

Prosty GUI w Pythonie dla VistulaOS (Arch) + Cinnamon:
- zakładka **System**: sprawdzanie i instalowanie aktualizacji pacmana
- zakładka **Flatpak**: sklep (szukanie/instalacja), lista zainstalowanych, zarządzanie remotes
- zakładka **Ustawienia**: przełączanie języka (PL/EN)

Aplikacja sama próbuje podczytać motyw GTK i ikony z Cinnamon.

## Sklep: kategorie

Sklep ładuje aplikacje z wybranego remote (np. `vistula`) i grupuje je w kategorie.
Kategorie to prosty filtr po AppID – konfiguracja w `~/.config/vistula-updater/config.json` (pole `categories`).

## Remotes: odinstalowywanie

W zakładce Remotes klikasz na remote i widzisz co masz z niego zainstalowane. Możesz to odinstalować.

Uwaga: w logach przed każdą komendą jest `$` – to tylko prefix do logowania, nie nazwa remote.

## Zależności (Arch)

Potrzebujesz:

```bash
sudo pacman -S --needed python gobject-introspection gtk3 python-gobject pacman-contrib polkit flatpak

> Dla powiadomień w tle potrzebujesz też `libnotify` (daje `notify-send`).
```

> `pacman-contrib` – dzięki temu masz `checkupdates` (wygodniejsze sprawdzanie aktualizacji).

## Uruchomienie

```bash
chmod +x run.sh
./run.sh
```

Skrypt ustawia `PYTHONPATH` żeby Python widział `src/`.

Albo ręcznie:

```bash
PYTHONPATH=$PWD/src python3 -m vistulla_updater.main

## Powiadomienia w tle (autostart)

Paczka instaluje autostart do `/etc/xdg/autostart/`, który uruchamia `vistula-updater-notifier` po zalogowaniu i sprawdza aktualizacje co godzinę.

Test ręczny (jednorazowo):

```bash
vistula-updater-notifier once
```
```

## Pakowanie i instalacja (Arch / VistulaOS)

Masz gotowe pliki do zbudowania paczki: `pyproject.toml`, `PKGBUILD` i plik desktop.

### 1) Co potrzebujesz do budowania

```bash
sudo pacman -S --needed base-devel python-build python-installer python-setuptools python-wheel
```

### 2) Zrób tarball ze źródeł

Jeśli masz gita i tagi:

```bash
git tag -a v0.1.0 -m "vistula-updater 0.1.0"
git archive --format=tar --prefix=vistula-updater-0.1.0/ v0.1.0 | gzip -9 > vistula-updater-0.1.0.tar.gz
```

Albo użyj skryptu:

```bash
chmod +x make-tarball.sh
./make-tarball.sh 0.1.0
```

Bez gita: spakuj katalog ręcznie tak żeby w środku był `vistula-updater-0.1.0/`.

### 3) Zbuduj paczkę

```bash
makepkg -s
```

### 4) Zainstaluj

```bash
sudo pacman -U vistula-updater-0.1.0-1-any.pkg.tar.zst
```

Potem uruchomisz z menu albo:

```bash
vistula-updater
```

### 5) Własne repo (lokalnie)

Możesz zrobić sobie repo w katalogu:

```bash
mkdir -p ~/repo/vistula
cp *.pkg.tar.zst ~/repo/vistula/
cd ~/repo/vistula
repo-add vistula.db.tar.gz ./*.pkg.tar.zst
```

Dodaj do `/etc/pacman.conf`:

```ini
[vistula]
SigLevel = Optional TrustAll
Server = file:///home/patryk/repo/vistula
```

I zainstaluj:

```bash
sudo pacman -Sy
sudo pacman -S vistula-updater
```

## Własny sklep Flatpak (czyli własny remote)

Sklep to frontend (GUI), aplikacje pobierasz z repozytorium (remote).

### 1) Dodaj remote na kliencie

Załóżmy że hostujesz repo pod `https://example.com/repo`:

```bash
flatpak remote-add --if-not-exists vistula https://example.com/repo
```

Potem szukasz i instalujesz co masz w swoim repo.

### 2) Jak zrobić repo Flatpak

Najprostsza droga:
- budujesz paczkę Flatpak (`flatpak-builder`)
- eksportujesz do repo (OSTree)
- wrzucasz katalog repo na HTTP(S)

Schemat:

```bash
flatpak-builder --force-clean build-dir com.example.App.json
flatpak build-export repo build-dir
flatpak build-update-repo repo
```

Repo musi być dostępne przez HTTP(S) jako katalog z plikami OSTree.

## Bezpieczeństwo

Aktualizacja systemu używa `pkexec pacman -Syu --noconfirm` – wygodne w GUI, ale automatyczne. Jeśli wolisz kontrolować co się instaluje, lepiej aktualizuj ręcznie w terminalu.

## Co dalej

Mogę dodać:
- zarządzanie remotes z poziomu GUI (dodawanie/usuwanie)
- lista zainstalowanych Flatpaków z przyciskiem "Uruchom"
- instalacja aktualizacji bez `--noconfirm` (przez terminal z interakcją)
