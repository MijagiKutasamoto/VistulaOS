#!/usr/bin/env bash
set -euo pipefail

# Aktualizuje repo pacmana w katalogu repo/vistula/os/x86_64 na podstawie paczek *.pkg.tar.*
#
# Użycie:
#   ./scripts/update-pacman-repo.sh /ścieżka/do/paczek
#
# Przykład (po buildzie makepkg):
#   ./scripts/update-pacman-repo.sh tools/vistula-updater

src_dir="${1:-}"
repo_dir="repo/vistula/os/x86_64"

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

cp -f "${pkgs[@]}" "$repo_dir/"

(
  cd "$repo_dir"
  repo-add -R vistula.db.tar.gz ./*.pkg.tar.*
)

echo "OK: zaktualizowano repo w $repo_dir" >&2
