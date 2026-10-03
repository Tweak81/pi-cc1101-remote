#!/bin/bash
set -euo pipefail

REPOSITORY="Tweak81/pi-cc1101-remote"
BRANCH="main"
INSTALL_DIR="${PI_RF_INSTALL_DIR:-$HOME/pi-cc1101-remote}"

if [ "$(id -u)" -eq 0 ]; then
  echo "Bitte ohne sudo starten; install.sh verwendet sudo gezielt selbst." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1; then
  echo "curl und tar werden benötigt. Raspberry Pi OS bringt beide normalerweise mit." >&2
  exit 1
fi

tmp_dir=$(mktemp -d)
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT INT TERM

archive="$tmp_dir/project.tar.gz"
curl --fail --silent --show-error --location \
  "https://api.github.com/repos/${REPOSITORY}/tarball/${BRANCH}" --output "$archive"

mkdir -p "$tmp_dir/project"
tar -xzf "$archive" --strip-components=1 -C "$tmp_dir/project"
if [ -e "$INSTALL_DIR" ]; then
  backup="${INSTALL_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
  mv "$INSTALL_DIR" "$backup"
  echo "Vorhandene Installation gesichert unter: $backup"
fi
mkdir -p "$(dirname "$INSTALL_DIR")"
mv "$tmp_dir/project" "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "Installiere Pi RF Logger nach $INSTALL_DIR …"
bash ./install.sh

if ! command -v nmcli >/dev/null 2>&1; then
  echo "NetworkManager/nmcli fehlt. Hotspot kann nicht eingerichtet werden." >&2
  echo "Bitte Raspberry Pi OS mit NetworkManager verwenden und danach setup-hotspot.sh ausführen." >&2
  exit 1
fi
sudo systemctl enable --now NetworkManager

printf "\nHotspot-Name (SSID) [Pi-RF-Logger]: "
IFS= read -r HOTSPOT_SSID < /dev/tty
HOTSPOT_SSID=${HOTSPOT_SSID:-Pi-RF-Logger}
printf "WLAN-Passwort (mindestens 8 Zeichen): "
stty -echo < /dev/tty
IFS= read -r HOTSPOT_PASSWORD < /dev/tty
stty echo < /dev/tty
printf "\n"
if [ "${#HOTSPOT_PASSWORD}" -lt 8 ]; then
  echo "Das Passwort muss mindestens 8 Zeichen lang sein." >&2
  exit 1
fi

export HOTSPOT_SSID HOTSPOT_PASSWORD
bash ./setup-hotspot.sh
unset HOTSPOT_PASSWORD

cat <<EOF

Installation fertig.
Weboberfläche: http://10.42.0.1:8080
WLAN: $HOTSPOT_SSID
Der Empfangsdienst und der Hotspot starten künftig automatisch.
Ein Neustart ist nötig, damit SPI vollständig aktiviert wird: sudo reboot
EOF
