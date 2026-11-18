#!/bin/sh
set -eu
umask 022
cd "$(dirname "$0")/.."

case "${1:-store}" in
    store) package=lan-proxy; other=lan-proxy-admin ;;
    admin) package=lan-proxy-admin; other=lan-proxy ;;
    *) echo "Usage: $0 [store|admin]" >&2; exit 2 ;;
esac
version=$(cat RELEASE_VERSION)
dpkg --validate-version "$version"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
root="$stage/root"
app="$root/usr/lib/lan-proxy"
units="$root/usr/lib/systemd/system"
launcher="$root/usr/share/APPLaunch"
doc="$root/usr/share/doc/$package"
install -d "$root/DEBIAN" "$app" "$units" "$launcher/applications" "$launcher/share/images" "$doc"
install -m 644 VERSION client.py core.py helper.py relay.py ui.py i18n.py "$app/"
install -m 644 icon.png "$launcher/share/images/lan-proxy.png"
sed 's|/usr/local/lib/lan-proxy/|/usr/lib/lan-proxy/|g' lan-proxy.desktop > "$app/lan-proxy.desktop"
install -m 644 "$app/lan-proxy.desktop" "$launcher/applications/lan-proxy.desktop"
install -m 644 lan-proxy.service lan-proxy.socket "$units/"
if [ "$package" = lan-proxy-admin ]; then
    install -m 644 packaging/admin/sync_badge.py "$app/"
    install -m 644 packaging/admin/lan-proxy-badge.service packaging/admin/lan-proxy-badge.path "$units/"
    install -m 644 icon-active.png "$launcher/share/images/lan-proxy-active.png"
    # The badge service can test for the marker. The credential file remains 0600.
    sed 's/^RuntimeDirectoryMode=0700$/RuntimeDirectoryMode=0711/' lan-proxy.service > "$units/lan-proxy.service"
fi
install -m 644 README.md "$doc/README.md"
install -m 644 packaging/copyright "$doc/copyright"
for hook in preinst postinst prerm; do
    source="packaging/$hook"
    if [ "$package" = lan-proxy-admin ] && [ -f "packaging/admin/$hook" ]; then
        source="packaging/admin/$hook"
    fi
    install -m 755 "$source" "$root/DEBIAN/$hook"
done
size=$(du -sk "$root/usr" | awk '{print $1}')
cat > "$root/DEBIAN/control" <<EOF
Package: $package
Version: $version
Architecture: arm64
Section: net
Priority: optional
Conflicts: zero-proxy, $other
Replaces: zero-proxy, $other
Maintainer: tongfei11 <tongfei11@users.noreply.github.com>
Depends: applaunch, python3, python3-pil, ca-certificates, curl, nftables, redsocks, systemd
Recommends: fonts-noto-cjk
Installed-Size: $size
Homepage: https://github.com/tongfei11/LANProxy
Description: LAN HTTP CONNECT and SOCKS5 client for Cardputer Zero
 Configure one LAN proxy and connect or disconnect from the launcher.
 The background service redirects public IPv4 TCP and DNS.
EOF
mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$root" "dist/${package}_${version}_arm64.deb"
