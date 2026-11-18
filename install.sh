#!/bin/sh
# Run on the device from a source checkout after installing redsocks.
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Run with sudo'; exit 1; }
[ -x /usr/sbin/redsocks ] || { echo "Install the Debian redsocks dependency first"; exit 1; }
if systemctl cat lan-proxy.service >/dev/null 2>&1; then
    systemctl stop lan-proxy.service
fi
install -d -m 755 /usr/local/lib/lan-proxy
install -m 644 core.py client.py helper.py relay.py ui.py i18n.py VERSION lan-proxy.desktop /usr/local/lib/lan-proxy/
chown -R root:root /usr/local/lib/lan-proxy
install -m 644 lan-proxy.service /etc/systemd/system/lan-proxy.service
install -m 644 lan-proxy.desktop /usr/share/APPLaunch/applications/lan-proxy.desktop
install -m 644 icon.png /usr/share/APPLaunch/share/images/lan-proxy.png
install -m 644 icon-active.png /usr/share/APPLaunch/share/images/lan-proxy-active.png
install -m 644 lan-proxy-reset.service /etc/systemd/system/lan-proxy-reset.service
systemctl daemon-reload
systemctl enable lan-proxy-reset.service
/usr/bin/python3 /usr/local/lib/lan-proxy/helper.py badge
# Does not enable automatic connection, alter launcher files, or restart the launcher.
