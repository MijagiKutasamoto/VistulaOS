#!/bin/bash
# Build script for vistula-updater-rs on Arch Linux

set -e

VERSION="${1:-1.3.0}"
RELEASE="${2:-1}"
ARCH="x86_64"

echo "Building vistula-updater-rs v$VERSION for Arch Linux..."

# Extract tarball
tar -xzf vistula-updater-rs-${VERSION}.tar.gz

cd tools/vistula-updater-rs

# Update PKGBUILD with version
sed -i "s/pkgver=.*/pkgver=$VERSION/" PKGBUILD
sed -i "s/pkgrel=.*/pkgrel=$RELEASE/" PKGBUILD

# Build package
if command -v makepkg &> /dev/null; then
    makepkg -s --noconfirm
    
    # Output package info
    PKG_FILE="vistula-updater-${VERSION}-${RELEASE}-any.pkg.tar.zst"
    if [ -f "$PKG_FILE" ]; then
        echo "✓ Package built successfully: $PKG_FILE"
        ls -lh "$PKG_FILE"
        
        # Calculate checksum
        sha256sum "$PKG_FILE" > "${PKG_FILE}.sha256"
        echo "✓ Checksum saved"
    fi
else
    echo "✗ makepkg not found. Are you on Arch Linux?"
    echo "Install base-devel: sudo pacman -S --needed base-devel"
    exit 1
fi

echo ""
echo "=== Installation ==="
echo "sudo pacman -U $PKG_FILE"
