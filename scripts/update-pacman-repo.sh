#!/usr/bin/env bash
set -euo pipefail

# Aktualizuje repo pacmana w katalogu repo/vistula/os/x86_64 na podstawie paczek *.pkg.tar.*
#
# Użycie:
#   ./scripts/update-pacman-repo.sh <katalog_z_paczkami>
#
# Przykład (po buildzie makepkg):
#   ./scripts/update-pacman-repo.sh tools/vistula-updater
#
# UWAGA (GitHub):
# - Pacman pobiera: <repo>.db i <repo>.files
# - Zwykle są symlinkami do .db.tar.gz/.files.tar.gz
# - GitHub "raw" nie obsługuje symlinków, więc tworzymy normalne pliki vistula.db/vistula.files.

src_dir="${1:-}"
repo_dir="repo/vistula/os/x86_64"

if ! command -v repo-add >/dev/null 2>&1; then
  echo "Brak narzędzia 'repo-add' (pakiet: pacman-contrib)." >&2
  echo "Zainstaluj na hoście: sudo pacman -S pacman-contrib" >&2
  exit 127
fi

if [[ -z "$src_dir" ]]; then
  echo "Użycie: $0 <katalog_z_paczkami>" >&2
  exit 2
fi

mkdir -p "$repo_dir"

shopt -s nullglob
pkgs=("$src_dir"/*.pkg.tar.*)
shopt -u nullglob

if (( ${#pkgs[@]} == 0 )); then
  echo "Brak paczek *.pkg.tar.* w: $src_dir" >&2
  exit 1
fi

# Make the repo directory deterministic: keep only the packages we just copied.
rm -f "$repo_dir"/*.pkg.tar.* || true
cp -f "${pkgs[@]}" "$repo_dir/"

(
  cd "$repo_dir"

  # Recreate DB from scratch to avoid repo-add deleting the just-copied package when filenames match.
  rm -f vistula.db vistula.db.tar.gz vistula.db.tar.gz.old \
        vistula.files vistula.files.tar.gz vistula.files.tar.gz.old || true

  repo-add vistula.db.tar.gz ./*.pkg.tar.*

  # Ensure .db/.files are regular files (not symlinks) for GitHub hosting.
  cp -f vistula.db.tar.gz vistula.db
  cp -f vistula.files.tar.gz vistula.files
)

echo "OK: zaktualizowano repo w $repo_dir" >&2
