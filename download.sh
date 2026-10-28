#! /bin/bash
set -e
echo "Downloading tailscale"
ARCH=$(uname -m)

echo "ARCH: $ARCH"
# map to available static tarballs on pkgs.tailscale.com
if [ "$ARCH" = "x86_64" ]; then
  ARCH="amd64"
fi
if [ "$ARCH" = "aarch64" ]; then
  ARCH="arm64"
fi
if [ "$ARCH" = "armv7l" ]; then
  ARCH="arm"
fi

URL="${PACKAGE_BASEURL}/tailscale_${VERSION}_${ARCH}.tgz"
echo "$URL"
apt-get update -qq
echo "Installing curl"
apt-get install curl -y
echo "Downloading tailscale"
curl -sSfL -o tailscale.tgz "$URL"
tar xzf tailscale.tgz
mkdir -p /tailscale-bin
cp "tailscale_${VERSION}_${ARCH}/tailscale" "tailscale_${VERSION}_${ARCH}/tailscaled" /tailscale-bin/
