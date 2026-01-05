# Vistula-Updater v1.3 (Rust)

Przepisana na Rust wersja GUI aktualizatora systemu dla VistulaOS (Arch) + Cinnamon.

**Status**: ✅ MVP Completed - Wszystkie 3 zakładki zaimplementowane

## ✨ Cechy

- ✅ **Multilingual support** - PL/EN (JSON-based, łatwo rozszerzalne)
- ✅ **System tab** - Sprawdzanie i instalowanie aktualizacji pacmana
- ✅ **Flatpak tab** - Wyszukiwanie, lista zainstalowanych, instalacja aplikacji
- ✅ **Settings tab** - Zmiana języka i motywu
- 🎨 **GUI** - Iced framework (Rust-native, cross-platform, WGPU renderer)
- 📦 **Pacman** - Integration z checkupdates i pacman -Syu
- 🎁 **Flatpak** - Integration z flatpak CLI (install, search, list)
- ⚡ **Async/Tokio** - Non-blocking operacje systemowe
- 🔒 **Privilege escalation** - pkexec dla operacji wymagających uprawnień
- 📢 **Notifier** - Background daemon ze sprawdzaniem aktualizacji co godzinę
- 🧪 **Unit tests** - Testy dla pacman, flatpak, i18n, config modułów


## TODO

- [x] Implement System tab (pacman updates)
- [x] Implement Flatpak tab (store, installed, remotes)
- [x] Implement Settings tab (language, theme)
- [x] Cinnamon theme detection (readl_cinnamon_theme)
- [x] Update checks in background (notifier.rs)
- [x] System tray integration (desktop files)
- [x] Unit tests for all modules
- [x] i18n with argument substitution
- [ ] Custom categories for store (future feature)
- [ ] Error handling & logging improvements
- [ ] Configuration file support
- [ ] More language support (DE, FR, etc.)

## License

Taka sama jak VistulaOS
