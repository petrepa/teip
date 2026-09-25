#!/usr/bin/env bash
# Install teip as an always-on print server on a Raspberry Pi (Raspberry Pi OS Lite) or any
# Debian/Ubuntu machine with systemd. Run from inside the cloned repo:
#
#     git clone https://github.com/petrepa/teip && cd teip && ./deploy/linux/install.sh
#
# Options:  --hostname NAME   also rename the machine, so the app is at http://NAME.local/
#           --port N          listen on N instead of 80
# Re-running is safe: it updates the environment, the config it wrote, and the service.
set -euo pipefail

HOSTNAME_NEW="" PORT=80
while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostname) HOSTNAME_NEW="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
USER_NAME="${SUDO_USER:-$USER}"
[[ "$USER_NAME" == root ]] && { echo "Run as your normal user (sudo is used where needed)." >&2; exit 1; }
cd "$REPO"

echo "== uv and the Python environment"
if ! command -v uv >/dev/null && [[ ! -x "$HOME/.local/bin/uv" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
"$UV" sync --no-dev   # installs Python 3.12+ itself if the system one is older

echo "== printer"
PRINTER=""
if command -v lsusb >/dev/null; then
  PID="$(lsusb -d 04f9: 2>/dev/null | head -1 | sed -E 's/.*04f9:([0-9a-f]{4}).*/\1/')"
  if [[ -n "$PID" ]]; then
    PRINTER="$("$REPO/.venv/bin/python" -c "from teip.printers import BY_PID; p = BY_PID.get(0x$PID); print(p.model if p else '')")"
  fi
fi
if [[ -z "$PRINTER" ]]; then
  echo "No supported printer found on USB. Using PT-E560BT; change 'printer' in config.toml later."
  PRINTER="PT-E560BT"
else
  echo "Found $PRINTER."
fi

if [[ ! -f config.toml ]] || grep -q "^# written by deploy/linux/install.sh" config.toml; then
  cat > config.toml <<TOML
# written by deploy/linux/install.sh; delete this line to keep your own edits on re-install
backend = "usb"
printer = "$PRINTER"
host = "0.0.0.0"
port = $PORT
TOML
else
  echo "Keeping your config.toml."
fi

echo "== USB access for $USER_NAME (udev rule)"
sudo tee /etc/udev/rules.d/60-teip.rules >/dev/null <<'RULE'
# teip: let the plugdev group use Brother printers without root.
SUBSYSTEM=="usb", ATTR{idVendor}=="04f9", MODE="0660", GROUP="plugdev"
RULE
sudo usermod -aG plugdev "$USER_NAME"
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=usb

echo "== systemd service"
sudo tee /etc/systemd/system/teip.service >/dev/null <<UNIT
[Unit]
Description=teip label print server
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
Group=plugdev
WorkingDirectory=$REPO
ExecStart=$REPO/.venv/bin/python serve.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
# lets a normal user listen on port 80
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now teip.service
sudo systemctl restart teip.service

if [[ -n "$HOSTNAME_NEW" ]]; then
  echo "== hostname $HOSTNAME_NEW"
  sudo hostnamectl set-hostname "$HOSTNAME_NEW"
  sudo sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME_NEW/" /etc/hosts
  sudo systemctl restart avahi-daemon 2>/dev/null || true
fi

NAME="${HOSTNAME_NEW:-$(hostname)}"
SUFFIX=""; [[ "$PORT" != 80 ]] && SUFFIX=":$PORT"
echo
echo "teip is running: http://$NAME.local$SUFFIX/"
echo "Logs:    journalctl -u teip -f"
echo "Update:  git pull && ./deploy/linux/install.sh"
