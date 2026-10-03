#!/bin/sh
set -eu
sudo raspi-config nonint do_spi 0
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  python3-pigpio python3-spidev python3-flask git build-essential network-manager

# Raspberry Pi OS Trixie no longer ships the pigpiod daemon as a binary
# package. On Pi Zero 2 W it still works, so build the pinned official v79
# release when the executable is absent. The Python client remains an APT
# package; this avoids modifying the system Python installation with pip.
if ! command -v pigpiod >/dev/null 2>&1; then
  pigpio_build=$(mktemp -d)
  trap 'rm -rf "$pigpio_build"' EXIT INT TERM
  git clone --depth 1 --branch v79 https://github.com/joan2937/pigpio.git "$pigpio_build"
  make -C "$pigpio_build"
  sudo install -m 0755 "$pigpio_build/pigpiod" /usr/local/bin/pigpiod
  sudo install -m 0755 "$pigpio_build/pigs" /usr/local/bin/pigs
  sudo install -m 0755 "$pigpio_build/libpigpio.so.1" /usr/local/lib/libpigpio.so.1
  sudo ln -sfn libpigpio.so.1 /usr/local/lib/libpigpio.so
  sudo ldconfig
fi

if ! systemctl list-unit-files pigpiod.service --no-legend 2>/dev/null | grep -q pigpiod; then
  sudo install -m 0644 pigpiod.service /etc/systemd/system/pigpiod.service
  sudo systemctl daemon-reload
fi
sudo systemctl enable --now pigpiod
mkdir -p signals
chmod +x rfcontrol.py webapp.py monitor.py setup-hotspot.sh
install_dir=$(pwd)
install_user=$(id -un)
sed -e "s|INSTALL_DIR|$install_dir|g" -e "s|INSTALL_USER|$install_user|g" \
  rfremote-web.service > /tmp/rfremote-web.service
sudo install -m 0644 /tmp/rfremote-web.service /etc/systemd/system/rfremote-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now rfremote-web.service
echo "Installation abgeschlossen. Bitte den Pi jetzt neu starten: sudo reboot"
