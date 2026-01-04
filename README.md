# VistulaOS
VistulaOS – Arch Linux based distribution with custom Cinnamon environment

## Repo pacmana

Dodaj do `/etc/pacman.conf`:

```
[vistula]
SigLevel = Optional TrustAll
Server = https://mijagikutasamoto.github.io/VistulaOS/repo/vistula/os/$arch
```

Odśwież i zainstaluj:

```
sudo pacman -Syy
sudo pacman -S vistula-updater
```
