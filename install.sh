#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/mac-filtering"
SERVICE_USER="unifi-mac-filter"
SERVICE_FILE="/etc/systemd/system/mac-filtering.service"
SERVICE_NAME="mac-filtering"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh"
  exit 1
fi

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

mkdir -p "${APP_DIR}"

tar --exclude=.venv --exclude=instance --exclude=.env --exclude=.git -cf - . | tar -C "${APP_DIR}" -xf -

mkdir -p "${APP_DIR}/instance/backups"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo "Created ${APP_DIR}/.env. Edit it before starting the service."
fi

if ! grep -q '^APP_NAME=' "${APP_DIR}/.env"; then
  printf '\nAPP_NAME="UniFi MAC Filtering"\n' >> "${APP_DIR}/.env"
fi

rm -rf "${APP_DIR}/.venv"
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip wheel
"${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

cp "${APP_DIR}/deploy/mac-filtering.service" "${SERVICE_FILE}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"

systemctl daemon-reload

echo "Installed to ${APP_DIR}"
echo "Next: edit ${APP_DIR}/.env, test UniFi API access, then start the service."
echo "  sudo nano ${APP_DIR}/.env"
echo "  sudo -u ${SERVICE_USER} ${APP_DIR}/.venv/bin/python ${APP_DIR}/scripts/test-unifi-api.py"
echo "  sudo systemctl enable --now ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME} --no-pager"
