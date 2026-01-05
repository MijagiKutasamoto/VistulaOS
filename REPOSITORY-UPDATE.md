# Repository Database Update Instructions

## Overview

This document explains how to update the VistulaOS package repository with the new `vistula-updater-rs v1.3.0` package.

## Prerequisites

- Arch Linux system with `pacman-contrib` installed
- Access to the repository directory (must be writable)
- GPG key for signing (optional but recommended)

## Steps

### 1. Build the Package

On an Arch Linux system:

```bash
cd /home/patryk/VistulaOS-Repo
bash build-arch-package.sh 1.3.0 1
```

This will create:
- `vistula-updater-1.3.0-1-any.pkg.tar.zst` (the package)
- `vistula-updater-1.3.0-1-any.pkg.tar.zst.sha256` (checksum)

### 2. Move Package to Repository

```bash
# Assuming you have access to the repo directory
cp tools/vistula-updater-rs/vistula-updater-1.3.0-1-any.pkg.tar.zst \
   repo/vistula/os/x86_64/

# Copy the old Python version as backup (optional)
# mv repo/vistula/os/x86_64/vistula-updater-0.1.2-1-any.pkg.tar.zst \
#    repo/vistula/os/x86_64/vistula-updater-0.1.2-1-any.pkg.tar.zst.old
```

### 3. Update Repository Database

Navigate to the repository directory:

```bash
cd repo/vistula/os/x86_64
```

#### Option A: Using `repo-add` (from pacman-contrib)

```bash
# Add the new package to the database
repo-add -s vistula.db.tar.gz vistula-updater-1.3.0-1-any.pkg.tar.zst

# This creates:
# - vistula.db (updated database)
# - vistula.db.tar.gz (compressed database)
# - vistula.files (file list)
# - vistula.files.tar.gz (compressed file list)
```

#### Option B: Rebuild from Scratch

```bash
# Remove old database files
rm -f vistula.db vistula.db.tar.gz vistula.files vistula.files.tar.gz

# Create new database with all packages
repo-add vistula.db.tar.gz *.pkg.tar.zst
```

### 4. Verify Repository

```bash
# List packages in database
tar -tzf vistula.db.tar.gz | grep -E "^[^/]+/$"

# Expected output should include:
# vistula-updater-1.3.0-1/
```

### 5. Push to GitHub

```bash
cd /home/patryk/VistulaOS-Repo

git add repo/vistula/os/x86_64/
git commit -m "repo: Update database with vistula-updater-rs 1.3.0"
git push upstream feature/vistula-updater-rs
```

## Testing

Users can test the repository with:

```bash
# Add the repository to /etc/pacman.conf
[vistula]
Server = https://raw.githubusercontent.com/MijagiKutasamoto/VistulaOS/feature/vistula-updater-rs/repo/vistula/os/$arch

# Install the package
sudo pacman -Sy
sudo pacman -S vistula-updater
```

## Verification Checklist

- [ ] Package builds successfully
- [ ] Package file is in correct location
- [ ] Repository database is updated
- [ ] Database contains correct package metadata
- [ ] Changes are pushed to GitHub
- [ ] All old Python version packages are backed up
- [ ] Users can sync and install the new package

## Rollback

If something goes wrong:

```bash
cd repo/vistula/os/x86_64

# Restore from backup
tar -xzf vistula.db.tar.gz.bak

# Or rebuild without the new package
rm vistula-updater-1.3.0-1-any.pkg.tar.zst
repo-add vistula.db.tar.gz *.pkg.tar.zst
```

## Note on Binary vs Source

The package contains:
- Pre-compiled binaries (release builds with LTO)
- i18n assets (JSON translations)
- Desktop integration files
- Autostart configuration for notifier

**No compilation is needed on the user's system.** The binary is fully static and self-contained.

---

For more information, see `RELEASE-1.3.0.md` and `tools/vistula-updater-rs/README.md`
