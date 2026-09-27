#!/usr/bin/env bash
# STB WiFi Panel installer for Armbian/Debian on Amlogic S905X (HG680P)
# Run as root:  curl -fsSL https://raw.githubusercontent.com/USER/stb-wifi-panel/main/install.sh | bash

set -euo pipefail

APP_DIR="/opt/stb-wifi-panel"
SERVICE_NAME="stb-wifi-panel"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_BIN="$(command -v python3)"

echo "== STB WiFi Panel installer =="
echo "Target dir: ${APP_DIR}"
echo "Service:    ${SERVICE_NAME}"
echo ""

# 1. check deps
need=(nmcli python3)
for c in "${need[@]}"; do
    if ! command -v "$c" >/dev/null; then
        echo "ERROR: '$c' tidak ditemukan. Install NetworkManager + python3 dulu."
        exit 1
    fi
done

# check python3-flask (try import)
if ! "$PYTHON_BIN" -c "import flask" 2>/dev/null; then
    echo "Flask belum terinstall. Coba install via apt..."
    apt-get update && apt-get install -y python3-flask || {
        echo "Gagal install python3-flask. Coba manual: apt install python3-flask"
        exit 1
    }
fi

# 2. create app dir & copy app.py (expects app.py in same dir as this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "${SCRIPT_DIR}/app.py" ]]; then
    echo "ERROR: app.py tidak ditemukan di ${SCRIPT_DIR}"
    exit 1
fi

mkdir -p "${APP_DIR}"
cp "${SCRIPT_DIR}/app.py" "${APP_DIR}/app.py"
chmod 644 "${APP_DIR}/app.py"

# 3. systemd unit
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=STB WiFi Panel (Flask + nmcli)
After=network-online.target NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${PYTHON_BIN} ${APP_DIR}/app.py
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

# hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
ReadWritePaths=${APP_DIR}

[Install]
WantedBy=multi-user.target
EOF

# 4. enable & start
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

# 5. status
sleep 1
echo ""
echo "== Service status =="
systemctl status "${SERVICE_NAME}" --no-pager || true

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "== Done =="
echo "Akses panel:  http://${IP}:8080"
echo "Logs:         journalctl -u ${SERVICE_NAME} -f"
echo "Restart:      systemctl restart ${SERVICE_NAME}"
echo ""
echo "Catatan:"
echo "  - Hotspot hanya 2.4 GHz (chipset S905X single-band)."
echo "  - Jika Wi-Fi macet: matikan switch di panel, tunggu 3 detik, nyalakan lagi."
echo "  - Pastikan eth0 terhubung ke internet agar hotspot bisa sharing."