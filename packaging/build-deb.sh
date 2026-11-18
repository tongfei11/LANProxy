#!/bin/sh
set -eu
umask 022
cd "$(dirname "$0")/.."

version=$(cat RELEASE_VERSION)
dpkg --validate-version "$version"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
root="$stage/root"
app="$root/usr/lib/lan-proxy"
units="$root/usr/lib/systemd/system"
launcher="$root/usr/share/APPLaunch"
doc="$root/usr/share/doc/lan-proxy"
install -d "$root/DEBIAN" "$app" "$units" "$launcher/applications" "$launcher/share/images" "$doc"
install -m 644 VERSION client.py core.py helper.py relay.py ui.py i18n.py "$app/"
install -m 644 icon.png "$launcher/share/images/lan-proxy.png"
install -m 644 icon-active.png "$launcher/share/images/lan-proxy-active.png"
sed 's|/usr/local/lib/lan-proxy/|/usr/lib/lan-proxy/|g' lan-proxy.desktop > "$app/lan-proxy.desktop"
install -m 644 "$app/lan-proxy.desktop" "$launcher/applications/lan-proxy.desktop"
for unit in lan-proxy.service lan-proxy-reset.service; do
    sed 's|/usr/local/lib/lan-proxy/|/usr/lib/lan-proxy/|g' "$unit" > "$units/$unit"
done
install -m 644 README.md "$doc/README.md"
install -m 644 packaging/copyright "$doc/copyright"
for hook in preinst postinst prerm postrm; do
    install -m 755 "packaging/$hook" "$root/DEBIAN/$hook"
done
size=$(du -sk "$root/usr" | awk '{print $1}')
cat > "$root/DEBIAN/control" <<EOF
Package: lan-proxy
Version: $version
Architecture: arm64
Section: net
Priority: optional
Conflicts: zero-proxy
Replaces: zero-proxy
Maintainer: tongfei11 <tongfei11@users.noreply.github.com>
Depends: applaunch, python3, python3-pil, ca-certificates, curl, nftables, redsocks, sudo, systemd
Recommends: fonts-noto-cjk
Installed-Size: $size
Homepage: https://github.com/tongfei11/LANProxy
Description: LAN HTTP CONNECT and SOCKS5 client for Cardputer Zero
 Configure one LAN proxy and connect or disconnect from the launcher.
 The background service redirects public IPv4 TCP and DNS.
EOF
mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$root" "dist/lan-proxy_${version}_arm64.deb"
