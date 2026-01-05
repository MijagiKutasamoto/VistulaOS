#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Keep the runtime hermetic: do not inherit PYTHONPATH from the shell.
# This avoids accidentally picking up a conflicting (pip/flatpak) Python environment.
export PYTHONPATH="$PWD/src"

# Preflight: detect broken/missing PyGObject early and print actionable diagnostics.
python3 - <<'PY'
import sys
import importlib.util

try:
	import gi  # type: ignore
except Exception as e:
	print("Brak modułu 'gi' (PyGObject) w tym interpreterze.")
	print("Python:", sys.executable)
	print("Błąd:", e)
	sys.exit(1)

if not hasattr(gi, "require_version"):
	spec = importlib.util.find_spec("gi")
	print("Wykryto 'gi' bez require_version (to nie jest poprawny PyGObject).")
	print("Python:", sys.executable)
	print("Spec gi:", spec)
	app_paths = [p for p in sys.path if p.startswith("/app/")]
	if app_paths:
		print("Wygląda na środowisko sandbox (np. VS Code z Flatpaka) — sys.path zawiera /app/…")
		for p in app_paths:
			print(" -", p)
		print("Rozwiązanie: uruchom program w terminalu systemowym (poza Flatpakiem) albo użyj VS Code instalowanego z pacmana/AUR.")
	else:
		print("Rozwiązanie (Arch): sudo pacman -S --needed python-gobject gtk3 gobject-introspection")
		print("oraz usuń ewentualne pipowe konflikty: python3 -m pip uninstall -y gi pygobject PyGObject")
	sys.exit(1)

PY

exec python3 -m vistulla_updater.main
