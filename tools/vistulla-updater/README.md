# Vistulla-updater (MVP)

Prosty GUI w Pythonie dla VistulaOS (Arch) + Cinnamon:
- zakładka **System**: sprawdzanie aktualizacji i aktualizacja przez `pacman`
- zakładka **Flatpak**: sklep (wyszukiwanie/instalacja), lista zainstalowanych, remotes (dodaj/ustaw domyślny + odinstaluj aplikacje z wybranego remote)
- zakładka **Ustawienia**: wybór języka (PL/EN)

Aplikacja automatycznie próbuje pobrać motyw (GTK + ikony) z ustawień Cinnamon.

## Sklep: kategorie

Sklep ładuje listę aplikacji z wybranego remote (np. `vistulla`) i pokazuje je w kategoriach.
Kategorie są prostym filtrem po AppID (konfiguracja w `~/.config/vistulla-updater/config.json`, pole `categories`).

## Remotes: odinstalowanie aplikacji

W zakładce Remotes wybierasz remote i widzisz aplikacje zainstalowane z tego remote — można je odinstalować.

Uwaga: w logach każda komenda jest poprzedzona prefiksem `$`. To tylko „prompt” logowania, a nie nazwa remote.

## Zależności (Arch)

Minimalnie:

```bash
sudo pacman -S --needed python gobject-introspection gtk3 python-gobject pacman-contrib polkit
sudo pacman -S --needed flatpak
```

> `pacman-contrib` daje komendę `checkupdates` (ładniejsze sprawdzanie aktualizacji).

## Uruchomienie

```bash
chmod +x run.sh
./run.sh
```

Skrypt ustawia `PYTHONPATH` tak, żeby Python widział katalog `src/`.

Alternatywnie (ręcznie):

```bash
PYTHONPATH=$PWD/src python3 -m vistulla_updater.main
```

## Pakowanie i instalacja (Arch / VistulaOS)

Projekt ma przygotowane pliki do zbudowania paczki pacmana: `pyproject.toml`, `PKGBUILD` i plik desktop.

### 1) Wymagania do budowania

```bash
sudo pacman -S --needed base-devel python-build python-installer python-setuptools python-wheel
```

### 2) Utwórz tarball źródeł (zalecane do repo)

Jeśli używasz gita i tagów:

```bash
git tag -a v0.1.0 -m "vistulla-updater 0.1.0"
git archive --format=tar --prefix=vistulla-updater-0.1.0/ v0.1.0 | gzip -9 > vistulla-updater-0.1.0.tar.gz
```

Albo prościej (skrypt w repo):

```bash
chmod +x make-tarball.sh
./make-tarball.sh 0.1.0
```

Jeśli nie używasz gita: spakuj katalog ręcznie tak, żeby w środku był folder `vistulla-updater-0.1.0/`.

### 3) Zbuduj paczkę

W katalogu projektu:

```bash
makepkg -s
```

### 4) Zainstaluj paczkę do systemu

```bash
sudo pacman -U vistulla-updater-0.1.0-1-any.pkg.tar.zst
```

Po instalacji uruchomisz aplikację z menu (plik `.desktop`) albo komendą:

```bash
vistulla-updater
```

### 5) Własne repo pacmana (lokalne)

Przykład prostego repo w katalogu:

```bash
mkdir -p ~/repo/vistulla
cp *.pkg.tar.zst ~/repo/vistulla/
cd ~/repo/vistulla
repo-add vistulla.db.tar.gz ./*.pkg.tar.zst
```

Dodaj do `/etc/pacman.conf`:

```ini
[vistulla]
SigLevel = Optional TrustAll
Server = file:///home/patryk/repo/vistulla
```

I zainstaluj:

```bash
sudo pacman -Sy
sudo pacman -S vistulla-updater
```

## Własny „sklep” Flatpak (czyli własny remote)

„Sklep” to w praktyce **frontend** (to GUI), a „Twoje aplikacje” pochodzą z **Twojego repozytorium (remote)**.

### 1) Dodaj remote na kliencie (VistulaOS)

Zakładam, że hostujesz repo pod URL (np. `https://example.com/repo`). Dodanie:

```bash
flatpak remote-add --if-not-exists vistulla https://example.com/repo
```

Potem w aplikacji możesz wyszukiwać i instalować (wyniki będą zależeć od tego, co jest w Twoim repo).

### 2) Jak zbudować repo Flatpak (skrót)

Najprostszy flow (na maszynie build):
- budujesz paczkę Flatpak (np. przez `flatpak-builder`)
- eksportujesz do repo (OSTree)
- publikujesz katalog repo na HTTP(S)

Przykładowo (schemat):

```bash
flatpak-builder --force-clean build-dir com.example.App.json
flatpak build-export repo build-dir
flatpak build-update-repo repo
```

Repo musi być dostępne po HTTP(S) jako katalog (z plikami OSTree).

## Uwagi bezpieczeństwa

- Aktualizacja systemu używa `pkexec pacman -Syu --noconfirm` (żeby działało z GUI bez terminala). To jest wygodne, ale agresywne — jeśli chcesz potwierdzać ręcznie, lepszy jest update z terminala.

## Następne kroki

Jeśli chcesz, mogę dopracować:
- obsługę własnego remote z poziomu GUI (dodaj/usuń)
- listę zainstalowanych Flatpaków + przycisk „Uruchom”
- instalację aktualizacji systemu w trybie transakcji (bez `--noconfirm`), np. przez uruchomienie w terminalu
