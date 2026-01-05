# Manual Packaging Guide for vistula-updater-rs v1.3.0

Since the build system requires Arch Linux with `pacman-contrib` and `base-devel`, this guide provides step-by-step instructions for creating the package manually.

## Prerequisites

- Arch Linux system
- `pacman-contrib` package installed (`sudo pacman -S pacman-contrib`)
- `base-devel` group installed (`sudo pacman -S base-devel`)
- `cargo` and Rust toolchain
- Source code from: https://github.com/MijagiKutasamoto/VistulaOS/tree/feature/vistula-updater-rs

## Step 1: Prepare Build Environment

```bash
# Clone or navigate to the repository
cd /tmp
git clone -b feature/vistula-updater-rs https://github.com/MijagiKutasamoto/VistulaOS.git vistula-build
cd vistula-build/tools/vistula-updater-rs

# Verify structure
ls -la
# Should show: PKGBUILD, src/, assets/, Cargo.toml, README.md
```

## Step 2: Build Using Makepkg

```bash
# Build the package (uses PKGBUILD)
makepkg -s

# This will:
# - Download source (if not present)
# - Compile with: cargo build --release
# - Run tests: cargo test --release
# - Create: vistula-updater-1.3.0-1-any.pkg.tar.zst

# After build completes:
ls -lh *.pkg.tar.zst
# Expected output: vistula-updater-1.3.0-1-any.pkg.tar.zst (~11MB)
```

## Step 3: Copy to Repository

```bash
# Copy the built package to repository
cp vistula-updater-1.3.0-1-any.pkg.tar.zst \
   ../../Vistula-Installer/repo/vistula/os/x86_64/

# Verify
ls -lh ../../Vistula-Installer/repo/vistula/os/x86_64/vistula-updater-1.3.0*
```

## Step 4: Update Repository Database

```bash
# Navigate to repository directory
cd ../../Vistula-Installer/repo/vistula/os/x86_64

# Add the new package to the database
repo-add -s vistula.db.tar.gz vistula-updater-1.3.0-1-any.pkg.tar.zst

# This creates/updates:
# - vistula.db (sqlite database)
# - vistula.db.tar.gz (compressed database)
# - vistula.files (file listing)
# - vistula.files.tar.gz (compressed file listing)

# Verify the package is in the database
tar -tzf vistula.db.tar.gz | grep vistula-updater-1.3.0
# Expected output:
# vistula-updater-1.3.0-1/desc
# vistula-updater-1.3.0-1/files
```

## Step 5: Verify Package Contents

```bash
# List what's inside the package
tar -tzf vistula-updater-1.3.0-1-any.pkg.tar.zst | head -20

# Should include:
# usr/bin/vistula-updater
# usr/bin/vistula-updater-notifier
# usr/share/applications/vistula-updater.desktop
# usr/share/applications/vistula-updater-notifier.desktop
# usr/share/vistula-updater/i18n/pl.json
# usr/share/vistula-updater/i18n/en.json
# etc/xdg/autostart/vistula-updater-notifier.desktop
```

## Step 6: Test Installation

```bash
# Install the package locally (optional, for testing)
sudo pacman -U vistula-updater-1.3.0-1-any.pkg.tar.zst

# Test the application
vistula-updater --help
vistula-updater  # Should launch GUI

# Check if notifier is installed
ls -la /usr/bin/vistula-updater*
```

## Step 7: Commit to Repository

```bash
# Go back to repository root
cd /path/to/VistulaOS-Repo

# Add changes
git add tools/Vistula-Installer/repo/vistula/os/x86_64/

# Commit
git commit -m "repo: Add vistula-updater-rs 1.3.0 to package repository"

# Push to GitHub
git push upstream feature/vistula-updater-rs
```

## Alternative: Using Automated Script

If `build-arch-package.sh` is available:

```bash
cd /path/to/VistulaOS-Repo
bash build-arch-package.sh 1.3.0 1

# This automates all steps except Step 4 (database update)
# You still need to run repo-add manually
```

## Troubleshooting

### Issue: `cargo: command not found`
```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.bashrc
```

### Issue: `repo-add: command not found`
```bash
# Install pacman-contrib
sudo pacman -S pacman-contrib
```

### Issue: Package size too large
```bash
# Strip the binary (already done in PKGBUILD)
# If recompiling, the PKGBUILD has: strip ${pkgdir}/usr/bin/*
# Final size should be: ~11MB for vistula-updater, ~1.1MB for notifier
```

### Issue: Database corruption
```bash
# Rebuild from scratch
cd repo/vistula/os/x86_64
rm vistula.db vistula.db.tar.gz vistula.files vistula.files.tar.gz
repo-add vistula.db.tar.gz *.pkg.tar.zst
```

## Expected Results

After following all steps:

```
repo/vistula/os/x86_64/
├── vistula-updater-0.1.2-1-any.pkg.tar.zst (old Python version)
├── vistula-updater-1.3.0-1-any.pkg.tar.zst (new Rust version) ← NEW
├── vistula.db (database)
├── vistula.db.tar.gz (compressed database)
├── vistula.files (file listing)
└── vistula.files.tar.gz (compressed file listing)
```

Users can then install with:
```bash
# Add to /etc/pacman.conf:
[vistula]
Server = https://raw.githubusercontent.com/MijagiKutasamoto/VistulaOS/feature/vistula-updater-rs/tools/Vistula-Installer/repo/vistula/os/$arch

# Install
sudo pacman -Sy
sudo pacman -S vistula-updater
```

## Support

For more information:
- [PKGBUILD Documentation](https://wiki.archlinux.org/title/PKGBUILD)
- [repo-add Manual](https://man.archlinux.org/man/repo-add.8.en)
- [VistulaOS Repository](https://github.com/MijagiKutasamoto/VistulaOS)

---

**Last Updated**: 2024-01-06
**Version**: 1.3.0
**Status**: Ready for Arch Linux packaging
