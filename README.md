# UniFi MAC Filtering

A small self-hosted dashboard for managing UniFi WiFi MAC filtering.

Built by [maxdorx](https://github.com/maxdorx/)

---

## Quick start

Install system packages:

```bash
sudo apt update
sudo apt install -y python3.12-venv python3-pip unzip git
```

Clone the repo:

```bash
git clone https://github.com/maxdorx/unifi-macfiltering-dashboard.git
cd unifi-macfiltering-dashboard
```

Install the app:

```bash
sudo ./install.sh
```

Generate a dashboard password hash:

```bash
sudo -u mac-filtering /opt/mac-filtering/.venv/bin/python /opt/mac-filtering/scripts/make-password-hash.py 'YourDashboardPasswordHere'
```

Generate an app secret:

```bash
openssl rand -hex 32
```

Edit the config:

```bash
sudo nano /opt/mac-filtering/.env
```

Set these values:

```bash
APP_NAME="UniFi MAC Filtering"
APP_USERNAME=admin
APP_PASSWORD_HASH=<generated password hash>
APP_SECRET_KEY=<generated app secret>
SESSION_MINUTES=60
DASHBOARD_TIMEZONE=Asia/Karachi

UNIFI_BASE_URL=https://127.0.0.1:8443
UNIFI_SITE=default
UNIFI_USERNAME=<local UniFi service account>
UNIFI_PASSWORD='<local UniFi service account password>'
UNIFI_VERIFY_SSL=false

HOST=0.0.0.0
PORT=4000
DATA_DIR=/opt/mac-filtering/instance
```

Test UniFi access:

```bash
sudo -u mac-filtering /opt/mac-filtering/.venv/bin/python /opt/mac-filtering/scripts/test-unifi-api.py
```

Start the service:

```bash
sudo systemctl enable --now mac-filtering
sudo systemctl status mac-filtering --no-pager
```

Open the dashboard:

```text
http://<server-ip>:4000
```

---

## What this project does

UniFi MAC Filtering gives support teams a simple web dashboard for managing UniFi WiFi MAC filtering.

It lets users:

* View WiFi networks.
* Check whether MAC filtering is on or off.
* View MAC addresses currently used for filtering.
* Add MAC addresses.
* Remove MAC addresses.
* Bulk import MAC addresses.
* Add names or owners to MAC addresses.
* Track who made each change.

The goal is simple: support users can manage WiFi MAC filtering without needing access to the full UniFi Network dashboard.

---

## Why this exists

UniFi supports MAC filtering, but managing it from the UniFi dashboard becomes painful when the list grows.

Adding MAC addresses in UniFi usually means opening WiFi settings, finding the MAC filtering section, adding entries manually, and saving the full WiFi network configuration. For support teams, that is slow, hard to audit, and easy to mess up.

This dashboard gives support users a safer workflow:

```text
Log in → choose WiFi network → add or remove MAC address → done
```

The app handles the UniFi API update in the background.

---

## Features

### WiFi network overview

* Shows UniFi WiFi networks.
* Shows whether each WiFi network is enabled.
* Shows security type in readable format.
* Shows whether MAC filtering is on or off.
* Shows MAC filtering policy.
* Shows the number of MAC addresses in the filtering list.
* Provides live search.

### MAC filtering management

* Add one MAC address.
* Add an optional name or owner.
* Remove MAC addresses.
* Edit saved names or owners.
* Search MAC addresses live while typing.
* Show 20 MAC addresses per page.
* Normalize common MAC formats.
* Prevent duplicate MAC entries.
* Validate MAC address format before saving.

Supported MAC formats:

```text
aa:bb:cc:dd:ee:ff
aa-bb-cc-dd-ee-ff
aabbccddeeff
```

### Bulk import

* Paste many MAC addresses at once.
* Upload CSV or TXT files.
* Preview changes before applying.
* Skip duplicates automatically.
* Save optional names or owners during import.
* Show invalid rows before applying.

Example bulk paste:

```text
32:17:57:9c:f6:22, maxdorx laptop
94-53-30-20-25-c1, Spare Dell
a864f1f49089
```

Example CSV:

```csv
mac,name
32:17:57:9c:f6:22,maxdorx laptop
94:53:30:20:25:c1,Spare Dell
a8:64:f1:f4:90:89,Test device
```

### Local names and owners

UniFi stores MAC addresses, but not friendly names for entries in the MAC filtering list.

This dashboard stores names and owners locally in SQLite.

Example:

```text
MAC address: 32:17:57:9c:f6:22
Name / owner: maxdorx laptop
```

### User accounts and roles

The dashboard has its own login system.

There are two account types.

#### Admin

Admins can:

* Add MAC addresses.
* Remove MAC addresses.
* Bulk import MAC addresses.
* Edit names and owners.
* Create manual backups.
* Download backups.
* Restore backups.
* View audit logs.
* Export audit logs.
* Create dashboard users.
* Disable or enable users.
* Reset user passwords.
* Change user roles.

#### Support

Support users can:

* View WiFi networks.
* View MAC filtering entries.
* Add MAC addresses.
* Remove MAC addresses.
* Bulk import MAC addresses.
* Edit names and owners.
* Change their own password.

Support users cannot access:

* Backups.
* Restore actions.
* Audit logs.
* User management.

### Audit log

The audit log records important actions.

Tracked actions include:

* MAC address added.
* MAC address removed.
* Bulk MAC import.
* Name or owner changed.
* Manual backup created.
* Backup restored.
* User account created.
* User password changed.
* User role changed.
* User account enabled or disabled.

Audit entries include:

* Time.
* Dashboard user.
* IP address.
* Action.
* WiFi network.
* MAC address or account.
* Name.
* Change details.
* Status.

### Backup and restore

The app creates a backup before changing a MAC filtering list.

Admins can also create manual backups.

Backups can be:

* Viewed.
* Downloaded.
* Restored.

Restore behavior:

```text
Restoring a backup replaces the current MAC filtering list with the MAC filtering list saved in that backup.
Use this only if you need to undo a bad change.
```

### Dark mode

The dashboard includes a dark mode toggle.

The selected theme is saved in the browser.

### Hardware MAC tip

The MAC management page shows a closable tip:

```text
Tip: Add the device hardware MAC address. Turn off randomized/private MAC on the user’s device before adding it.
```

This matters because many modern devices use randomized or private MAC addresses by default.

---

## How it works

The app talks to the UniFi Network Application using the local legacy API.

It logs into UniFi using a dedicated local UniFi admin or service account, then reads and updates WiFi network configuration.

The app uses these UniFi endpoints:

```text
POST /api/login
GET  /api/s/<site>/rest/wlanconf
GET  /api/s/<site>/rest/wlanconf/<wlan_id>
PUT  /api/s/<site>/rest/wlanconf/<wlan_id>
```

The app only changes these MAC filtering fields:

```text
mac_filter_enabled
mac_filter_policy
mac_filter_list
```

Everything else in the UniFi WiFi configuration is preserved.

Dashboard users do not get direct access to UniFi credentials. UniFi credentials stay server-side in the `.env` file.

---

## Compatibility

Tested with:

```text
UniFi Network Application 10.4.57
Self-hosted UniFi Network Application
```

Expected to work with:

```text
Self-hosted UniFi Network Application installs
```

Not currently designed for:

```text
UniFi official API-key-only integrations
UniFi cloud-only access
Remote UniFi Site Manager access
UI.com accounts with MFA
UniFi accounts that require 2FA/MFA
```

Use a local UniFi service account without MFA.

Recommended UniFi account:

```text
Type: Local UniFi admin/service account
MFA: Disabled
Access: Permission to edit WiFi settings
```

---

## Requirements

Server requirements:

```text
Linux
Python 3.12+
python3-venv
pip
systemd
Network access to the UniFi Network Application
```

Python packages are installed from `requirements.txt`.

---

## Configuration reference

The app uses:

```text
/opt/mac-filtering/.env
```

Example:

```bash
APP_NAME="UniFi MAC Filtering"
APP_USERNAME=admin
APP_PASSWORD_HASH=change_me
APP_SECRET_KEY=change_me
SESSION_MINUTES=60
DASHBOARD_TIMEZONE=Asia/Karachi

UNIFI_BASE_URL=https://127.0.0.1:8443
UNIFI_SITE=default
UNIFI_USERNAME=unifi-mac-filter
UNIFI_PASSWORD='change_me'
UNIFI_VERIFY_SSL=false

HOST=0.0.0.0
PORT=4000
DATA_DIR=/opt/mac-filtering/instance
```

### Environment variables

| Variable             | Purpose                                                                                  |
| -------------------- | ---------------------------------------------------------------------------------------- |
| `APP_NAME`           | Dashboard title shown in the web UI.                                                     |
| `APP_USERNAME`       | Bootstrap username for the first admin account. Used only when the users table is empty. |
| `APP_PASSWORD_HASH`  | Bootstrap password hash for the first admin account.                                     |
| `APP_SECRET_KEY`     | Flask session secret. Generate with `openssl rand -hex 32`.                              |
| `SESSION_MINUTES`    | Login session length in minutes.                                                         |
| `DASHBOARD_TIMEZONE` | Timezone used for displayed timestamps.                                                  |
| `UNIFI_BASE_URL`     | Base URL for the UniFi Network Application.                                              |
| `UNIFI_SITE`         | UniFi site name. Usually `default`.                                                      |
| `UNIFI_USERNAME`     | Local UniFi service account username.                                                    |
| `UNIFI_PASSWORD`     | Local UniFi service account password.                                                    |
| `UNIFI_VERIFY_SSL`   | Set to `false` for self-signed UniFi certificates.                                       |
| `HOST`               | Bind address for the dashboard.                                                          |
| `PORT`               | Dashboard port.                                                                          |
| `DATA_DIR`           | Directory for SQLite database and backups.                                               |

Password values containing special characters such as `#`, `$`, `!`, or spaces should be wrapped in single quotes.

Example:

```bash
UNIFI_PASSWORD='password,with#symbols'
```

---

## Upgrade

Pull the new version, then run:

```bash
cd unifi-macfiltering-dashboard
git pull
sudo ./install.sh
sudo systemctl restart mac-filtering
```

The installer preserves:

```text
.env
instance/
users
audit logs
MAC names
backups
UniFi credentials
```

---

## File structure

```text
unifi-macfiltering-dashboard/
├── app.py
├── run.py
├── wsgi.py
├── unifi_client.py
├── requirements.txt
├── install.sh
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
│
├── scripts/
│   ├── make-password-hash.py
│   └── test-unifi-api.py
│
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── ssid.html
│   ├── bulk_preview.html
│   ├── users.html
│   ├── audit.html
│   ├── backups.html
│   └── account.html
│
├── static/
│   └── style.css
│
└── deploy/
    └── mac-filtering.service
```

Installed runtime layout:

```text
/opt/mac-filtering/
├── .env
├── .venv/
├── app.py
├── run.py
├── unifi_client.py
├── templates/
├── static/
├── scripts/
└── instance/
    ├── mac_filtering.sqlite
    └── backups/
```

---

## Important files

### `app.py`

Main Flask application.

Handles:

* Dashboard routes.
* Login/logout.
* User accounts.
* Role checks.
* Password changes.
* MAC add/remove.
* Bulk import.
* Audit log.
* Backup and restore.
* Local MAC names.

### `unifi_client.py`

UniFi API client.

Handles:

* Login to UniFi.
* Reading WiFi network configuration.
* Updating MAC filtering lists.
* Restoring saved MAC filtering backups.
* Redacting sensitive UniFi fields before writing backups.

### `run.py`

Production entry point.

Starts the app using Waitress.

### `templates/`

HTML templates for the web UI.

### `static/style.css`

Dashboard styling, including light mode and dark mode.

### `scripts/make-password-hash.py`

Generates password hashes for dashboard users.

### `scripts/test-unifi-api.py`

Tests UniFi login and WiFi network read access.

### `instance/mac_filtering.sqlite`

Local SQLite database.

---

## License

MIT License.

This project is not affiliated with, endorsed by, or sponsored by Ubiquiti Inc. UniFi is a trademark of Ubiquiti Inc.
