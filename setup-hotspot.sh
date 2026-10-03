#!/bin/sh
set -eu

CONNECTION_NAME="pi-rf-hotspot"

if ! command -v nmcli >/dev/null 2>&1; then
  echo "NetworkManager/nmcli ist nicht installiert. Dieses Skript erwartet Raspberry Pi OS mit NetworkManager." >&2
  exit 1
fi
sudo systemctl enable --now NetworkManager

HOTSPOT_SSID=${HOTSPOT_SSID:-}
HOTSPOT_PASSWORD=${HOTSPOT_PASSWORD:-}
if [ -z "$HOTSPOT_SSID" ]; then
  printf "Hotspot-Name (SSID): "
  read -r HOTSPOT_SSID
fi
if [ -z "$HOTSPOT_SSID" ]; then
  echo "Die SSID darf nicht leer sein." >&2
  exit 1
fi
if [ -z "$HOTSPOT_PASSWORD" ]; then
  printf "WLAN-Passwort (mindestens 8 Zeichen): "
  stty -echo
  read -r HOTSPOT_PASSWORD
  stty echo
  printf "\n"
fi
if [ "${#HOTSPOT_PASSWORD}" -lt 8 ]; then
  echo "Das Passwort muss mindestens 8 Zeichen lang sein." >&2
  exit 1
fi

if nmcli -t -f NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
  sudo nmcli connection delete "$CONNECTION_NAME"
fi

sudo nmcli device wifi hotspot ifname wlan0 con-name "$CONNECTION_NAME" \
  ssid "$HOTSPOT_SSID" password "$HOTSPOT_PASSWORD"
sudo nmcli connection modify "$CONNECTION_NAME" connection.autoconnect yes
sudo nmcli connection up "$CONNECTION_NAME"

cat <<'EOF'
Der Pi stellt jetzt den WLAN-Hotspot bereit. Verbinde das iPhone mit diesem WLAN
und öffne http://10.42.0.1:8080. Die bisherige WLAN-Client-Verbindung des Pi wird
auf wlan0 durch den Hotspot ersetzt; ein separater Internetzugang bleibt unberührt.
EOF
