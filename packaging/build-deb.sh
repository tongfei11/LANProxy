#!/bin/sh
set -eu
umask 022
cd "$(dirname "$0")/.."

version=$(cat RELEASE_VERSION)
dpkg --validate-version "$version"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
root="$stage/root"
app="$root/usr/lib/zero-proxy"
units="$root/usr/lib/systemd/system"
launcher="$root/usr/share/APPLaunch"
doc="$root/usr/share/doc/zero-proxy"
install -d "$root/DEBIAN" "$app" "$units" "$launcher/applications" "$launcher/share/images" "$doc"
install -m 644 VERSION client.py core.py helper.py relay.py ui.py "$app/"
install -m 644 icon.png "$launcher/share/images/zero-proxy.png"
install -m 644 icon-active.png "$launcher/share/images/zero-proxy-active.png"
sed 's|/usr/local/lib/zero-proxy/|/usr/lib/zero-proxy/|g' zero-proxy.desktop > "$app/zero-proxy.desktop"
install -m 644 "$app/zero-proxy.desktop" "$launcher/applications/zero-proxy.desktop"
for unit in zero-proxy.service zero-proxy-reset.service; do
    sed 's|/usr/local/lib/zero-proxy/|/usr/lib/zero-proxy/|g' "$unit" > "$units/$unit"
done
install -m 644 README.md "$doc/README.md"
install -m 644 packaging/copyright "$doc/copyright"
for hook in preinst postinst prerm postrm; do
    install -m 755 "packaging/$hook" "$root/DEBIAN/$hook"
done
size=$(du -sk "$root/usr" | awk '{print $1}')
cat > "$root/DEBIAN/control" <<EOF
Package: zero-proxy
Version: $version
Architecture: arm64
Section: net
Priority: optional
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
dpkg-deb --root-owner-group -Zxz --build "$root" "dist/zero-proxy_${version}_arm64.deb"
