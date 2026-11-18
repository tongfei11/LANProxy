#!/bin/sh
# Development install uses the same layout and privileges as the Debian package.
set -eu
cd "$(dirname "$0")"
sh packaging/build-deb.sh
sudo apt install "./dist/lan-proxy_$(cat RELEASE_VERSION)_arm64.deb"
