# UniFi MAC Filtering

A small self-hosted dashboard for managing UniFi WiFi MAC allow lists without giving support users access to the UniFi Network dashboard.

Built by [maxdorx](https://github.com/maxdorx/)

---

## Quick start

Install the system packages:

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
sudo -u unifi-mac-filter /opt/mac-filtering/.venv/bin/python /opt/mac-filtering/scripts/make-password-hash.py 'YourDashboardPasswordHere'
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
APP_USERNAME=admin
APP_PASSWORD_HASH=<generated password hash>
APP_SECRET_KEY=<generated app secret>

UNIFI_BASE_URL=https://127.0.0.1:8443
UNIFI_SITE=default
UNIFI_USERNAME=<local UniFi service account>
UNIFI_PASSWORD='<local UniFi service account password>'
UNIFI_VERIFY_SSL=false

HOST=0.0.0.0
PORT=4000
DATA_DIR=/opt/mac-filtering/instance
DASHBOARD_TIMEZONE=Asia/Karachi
```

Test UniFi access:

```bash
sudo -u unifi-mac-filter /opt/mac-filtering/.venv/bin/python /opt/mac-filtering/scripts/test-unifi-api.py
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

UniFi MAC Filtering lets a helpdesk or support team add, remove, search, and bulk-import allowed device MAC addresses for UniFi WiFi networks.

It is designed for environments where WiFi access is controlled by MAC allow lists, but support users should not have full access to the UniFi Network dashboard.

Instead of giving support staff UniFi admin access, this app provides a limited web portal where they can manage only the MAC address lists.

---

## Why this exists

UniFi supports MAC filtering, but the built-in dashboard is not ideal for delegated support workflows.

UniFi’s built-in MAC filtering interface works, but it becomes painful when the list grows. Adding MAC addresses through the UniFi dashboard usually means opening the WiFi settings drawer, scrolling through the MAC filtering section, adding entries one by one, and saving the full WiFi network configuration. For a large helpdesk workflow, that is slow, hard to audit, and easy to mess up.

This project provides a simpler workflow: support users log in, choose a WiFi network, add or remove MAC addresses, and the app updates the UniFi MAC allow list through the local UniFi API.

Common problems this project solves:

- Support users need to add laptop MAC addresses without full UniFi dashboard access.
- UniFi MAC lists do not support owner names or device labels.
- Bulk MAC address import is awkward.
- Auditing who added or removed a MAC is difficult.
- Backups and restore points for MAC allow lists are useful before changes.
- Large MAC lists become hard to search and manage.

This dashboard adds the missing operational layer on top of UniFi’s MAC filtering feature.

---

## Main features

### WiFi network overview

- Shows UniFi WiFi networks.
- Shows whether each WiFi network is enabled.
- Shows security type in readable format.
- Shows whether the MAC allow list is on or off.
- Shows MAC allow policy.
- Shows the number of allowed MAC addresses.
- Provides live filtering and search.

### MAC address management

- Add one MAC address.
- Add an optional name or owner.
- Remove MAC addresses.
- Edit saved names or owners.
- Search MAC addresses live while typing.
- Show MAC addresses with pagination.
- Display 20 MAC addresses per page.
- Normalize common MAC formats.
- Prevent duplicate MAC entries.
- Validate MAC address format before saving.

Supported MAC formats include:

```text
aa:bb:cc:dd:ee:ff
aa-bb-cc-dd-ee-ff
aabbccddeeff
```

### Bulk import

- Paste many MAC addresses at once.
- Upload CSV or TXT files.
- Preview bulk changes before applying.
- Skip duplicates automatically.
- Save optional names or owners during import.
- Show invalid rows before applying.

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

UniFi stores only the MAC address list.

This dashboard stores names and owners locally in SQLite so support users can see who or what each MAC address belongs to.

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

- Add MAC addresses.
- Remove MAC addresses.
- Bulk import MAC addresses.
- Edit names and owners.
- Create manual backups.
- Download backups.
- Restore backups.
- View audit logs.
- Export audit logs.
- Create dashboard users.
- Disable or enable users.
- Reset user passwords.
- Change user roles.

#### Support

Support users can:

- View WiFi networks.
- View allowed MAC addresses.
- Add MAC addresses.
- Remove MAC addresses.
- Bulk import MAC addresses.
- Edit names and owners.
- Change their own password.

Support users cannot access:

- Backups.
- Restore actions.
- Audit logs.
- User management.

### Audit log

The audit log records important actions, including:

- MAC address added.
- MAC address removed.
- Bulk MAC import.
- Name or owner changed.
- Manual backup created.
- Backup restored.
- User account created.
- User password changed.
- User role changed.
- User account enabled or disabled.

Audit entries include:

- Time.
- Dashboard user.
- IP address.
- Action.
- WiFi network.
- MAC address or account.
- Name.
- Change details.
- Status.

Timestamps are displayed in the configured dashboard timezone.

### Backup and restore

The app creates a backup before changing a MAC list.

Admins can also create manual backups.

Backups can be:

- Viewed.
- Downloaded.
- Restored.

Restore behavior:

```text
Restoring a backup replaces the current MAC list with the MAC list saved in that backup.
Use this only if you need to undo a bad change.
```

### Dark mode

The dashboard includes a dark mode toggle.

Theme preference is saved in the browser.

### Hardware MAC tip

The MAC management page shows a closable tip:

```text
Tip: Add the device hardware MAC address. Turn off randomized/private MAC on the user’s device before adding it.
```

This matters because many modern devices use randomized or private MAC addresses by default.

---

## How it works

This app talks to the UniFi Network Application using the local legacy API.

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

The app does not give dashboard users direct access to UniFi credentials. UniFi credentials stay server-side in the `.env` file.

---

## Compatibility

Tested with:

```text
UniFi Network Application 10.4.57
Self-hosted UniFi Network Application
Legacy local API login
Default site path: /api/s/default/rest/wlanconf
```

Expected to work with:

```text
Self-hosted UniFi Network Application installs that support /api/login and /api/s/<site>/rest/wlanconf
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
Username: unifi-mac-filter
Type: Local UniFi admin/service account
MFA: Disabled
Access: Enough permission to edit WiFi settings
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

Python packages are installed automatically from `requirements.txt`.

---

## Installation

Install required system packages first:

```bash
sudo apt update
sudo apt install -y python3.12-venv python3-pip unzip git
```

Clone the project:

```bash
git clone https://github.com/maxdorx/unifi-macfiltering-dashboard.git
cd unifi-macfiltering-dashboard
```

Run the installer:

```bash
sudo ./install.sh
```

The app installs to:

```text
/opt/mac-filtering
```

The systemd service is:

```text
mac-filtering.service
```

---

## Configuration

Edit the `.env` file:

```bash
sudo nano /opt/mac-filtering/.env
```

Example configuration:

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

Generate a dashboard password hash:

```bash
sudo -u unifi-mac-filter /opt/mac-filtering/.venv/bin/python /opt/mac-filtering/scripts/make-password-hash.py 'YourPasswordHere'
```

Generate an app secret:

```bash
openssl rand -hex 32
```

Set these values in `.env`:

```bash
APP_PASSWORD_HASH=<generated password hash>
APP_SECRET_KEY=<generated secret>
```

Password values containing special characters such as `#`, `$`, `!`, or spaces should be wrapped in single quotes.

Example:

```bash
UNIFI_PASSWORD='password,with#symbols'
```

---

## Test UniFi API access

Before starting the service, test the UniFi connection:

```bash
sudo -u unifi-mac-filter /opt/mac-filtering/.venv/bin/python /opt/mac-filtering/scripts/test-unifi-api.py
```

Expected output:

```text
UniFi login OK. Site=default. SSIDs found: 3
```

The word `SSIDs` may appear in the test script output because UniFi uses that wording internally. The web UI uses clearer WiFi wording.

---

## Start the service

Enable and start the service:

```bash
sudo systemctl enable --now mac-filtering
```

Check status:

```bash
sudo systemctl status mac-filtering --no-pager
```

Open the dashboard:

```text
http://<server-ip>:4000
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

After upgrading, hard refresh the browser:

```text
Ctrl + F5
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

- Dashboard routes.
- Login/logout.
- User accounts.
- Role checks.
- Password changes.
- MAC add/remove.
- Bulk import.
- Audit log.
- Backup and restore.
- Local MAC names.

### `unifi_client.py`

UniFi API client.

Handles:

- Login to UniFi.
- Reading WiFi network configuration.
- Updating MAC allow lists.
- Restoring saved MAC list backups.
- Redacting sensitive UniFi fields before writing backups.

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

Stores:

- Dashboard users.
- User roles.
- Local MAC names.
- Audit log.
- Backup metadata.

### `instance/backups/`

Stores JSON backups created before MAC list changes.

---

## Security notes

Do not expose this dashboard directly to the internet.

Recommended deployment:

```text
LAN only
VPN only
Reverse proxy with HTTPS
Firewall-restricted access
Dedicated local UniFi service account
Strong dashboard passwords
```

Do not commit these files:

```text
.env
instance/
*.sqlite
backups/
logs
real MAC address exports
```

The included `.gitignore` excludes these files.

---

## Data storage

UniFi stores:

```text
MAC allow list
MAC filtering enabled/disabled state
MAC filtering policy
```

This app stores locally:

```text
Dashboard users
User roles
Local MAC names/owners
Audit log
Backup metadata
Backup files
```

Names and owners are not stored in UniFi.

---

## Limitations

- This project uses UniFi’s legacy local API endpoints.
- It requires a local UniFi account that can log in without MFA.
- It does not use the newer official UniFi API key system.
- It only manages WiFi MAC allow lists.
- It does not manage RADIUS MAC authentication.
- It does not manage VLAN assignment.
- It does not manage client blocking.
- It does not change WiFi passwords or security settings.
- Restore replaces the MAC list with the saved backup version.
- Large MAC lists may be better managed with RADIUS in enterprise environments.

---

## Troubleshooting

### UniFi login fails with `api.err.Invalid`

Check:

```text
UNIFI_USERNAME
UNIFI_PASSWORD
UNIFI_BASE_URL
UNIFI_SITE
```

Also check whether the password contains special characters. Wrap it in single quotes in `.env`.

Example:

```bash
UNIFI_PASSWORD='password,with#symbols'
```

### UniFi login fails with `api.err.Ubic2faTokenRequired`

The UniFi account has MFA enabled.

Use a local UniFi service account without MFA.

### Service fails with `Address already in use`

Another process is already using port `4000`.

Check:

```bash
sudo ss -ltnp | grep ':4000'
```

Restart the service:

```bash
sudo systemctl restart mac-filtering
```

### Dashboard changes do not show after upgrade

Hard refresh the browser:

```text
Ctrl + F5
```

### Check logs

```bash
sudo journalctl -u mac-filtering -n 100 --no-pager
```

---

## Open-source publishing checklist

Before publishing a fork or copy, remove:

```text
.env
instance/
SQLite database files
backup files
audit exports
real MAC addresses
real user names
server IP addresses
UniFi usernames
password hashes
company branding
```

Search for secrets before pushing:

```bash
grep -RniE 'password|secret|token|key|10\.|x_passphrase|unifi-cookie|pbkdf2' .
```

Expected matches may include source code that intentionally mentions password hashing or UniFi redaction. Do not commit real credentials or real runtime data.

---

## License

MIT License.

MIT is a good fit for this project because it is simple, widely used, and lets other admins use, modify, and deploy the tool with minimal restrictions.

---

## Credits

Built by [maxdorx](https://github.com/maxdorx/)

This project is not affiliated with, endorsed by, or sponsored by Ubiquiti Inc. UniFi is a trademark of Ubiquiti Inc.
