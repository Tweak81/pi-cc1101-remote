#!/bin/bash
set -euo pipefail

REPOSITORY="Tweak81/pi-cc1101-remote"
BRANCH="main"
INSTALL_DIR="${PI_RF_INSTALL_DIR:-$HOME/pi-cc1101-remote}"

if [ ! -d "$INSTALL_DIR" ] || [ ! -f "$INSTALL_DIR/webapp.py" ]; then
  echo "Installation nicht gefunden: $INSTALL_DIR" >&2
  echo "Bei abweichendem Installationsort PI_RF_INSTALL_DIR setzen." >&2
  exit 1
fi
if [ "$(id -u)" -eq 0 ]; then
  echo "Bitte ohne sudo starten; nur der Dienstneustart verwendet sudo." >&2
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

# Overlay the new tracked source. Runtime state such as saved captures,
# monitor configuration and hotspot settings stays in place.
cp -a "$tmp_dir/project/." "$INSTALL_DIR/"
sudo systemctl restart rfremote-web.service
sudo systemctl is-active --quiet rfremote-web.service
echo "Pi RF Logger aktualisiert. Der Webdienst ist aktiv."
