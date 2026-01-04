#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./make-tarball.sh 0.1.0
# Creates: vistulla-updater-0.1.0.tar.gz

pkgname="vistulla-updater"
version="${1:-}"

if [[ -z "$version" ]]; then
  echo "Użycie: $0 <wersja>, np. $0 0.1.0" >&2
  exit 2
fi

tarball="${pkgname}-${version}.tar.gz"
prefix="${pkgname}-${version}/"

# Prefer git-archive if we're in a git repo.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # If a matching tag exists, use it; else use current HEAD.
  ref="v${version}"
  if ! git rev-parse -q --verify "refs/tags/${ref}" >/dev/null 2>&1; then
    ref="HEAD"
  fi
  echo "Tworzę tarball z gita (ref: ${ref}) -> ${tarball}" >&2
  git archive --format=tar --prefix="${prefix}" "${ref}" | gzip -9 > "${tarball}"
else
  echo "Brak repo gita — tworzę tarball z katalogu roboczego -> ${tarball}" >&2
  # Create a tarball from the working directory, but ensure the correct top-level prefix.
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT

  mkdir -p "${tmpdir}/${prefix}"
  cp -a . "${tmpdir}/${prefix}"

  # Remove common junk from the temp copy.
  rm -rf "${tmpdir}/${prefix}.git" \
         "${tmpdir}/${prefix}.venv" \
         "${tmpdir}/${prefix}__pycache__" \
         "${tmpdir}/${prefix}dist" \
         "${tmpdir}/${prefix}build" || true

  find "${tmpdir}/${prefix}" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "${tmpdir}/${prefix}" -name '*.pyc' -type f -delete 2>/dev/null || true
  find "${tmpdir}/${prefix}" -name '*.pkg.tar.*' -type f -delete 2>/dev/null || true
  rm -f "${tmpdir}/${prefix}${tarball}" 2>/dev/null || true

  (cd "$tmpdir" && tar -czf "$OLDPWD/${tarball}" "${prefix}")
fi

echo "OK: ${tarball}" >&2
