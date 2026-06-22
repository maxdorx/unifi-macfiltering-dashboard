from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from unifi_client import UniFiClient, UniFiError

MAC_PATTERN = re.compile(r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|[0-9a-f]{12}|(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.@-]{2,64}$")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_mac(raw: str) -> str:
    if raw is None:
        raise ValueError("MAC is required")
    candidate = raw.strip().lower()
    match = MAC_PATTERN.search(candidate)
    if not match:
        raise ValueError(f"Invalid MAC address: {raw}")
    cleaned = re.sub(r"[^0-9a-f]", "", match.group(0).lower())
    if len(cleaned) != 12:
        raise ValueError(f"Invalid MAC address: {raw}")
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


def clean_label(raw: str | None) -> str:
    label = (raw or "").strip()
    label = re.sub(r"\s+", " ", label)
    return label[:120]


def clean_username(raw: str | None) -> str:
    username = (raw or "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username must be 2-64 characters and may contain letters, numbers, dot, underscore, dash, @.")
    return username


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def display_datetime(value: Any) -> str:
    """Render stored UTC ISO timestamps in the configured dashboard timezone."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        tz_name = current_app.config.get("DISPLAY_TIMEZONE", "Asia/Karachi")
        try:
            tz = ZoneInfo(str(tz_name))
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("Asia/Karachi")
        local = parsed.astimezone(tz)
        suffix = "PKT" if str(tz_name) == "Asia/Karachi" else local.tzname() or str(tz_name)
        return local.strftime("%d %b %Y, %I:%M:%S %p ") + suffix
    except Exception:
        return raw




ACTION_LABELS = {
    "add": "MAC added",
    "add_failed": "MAC add failed",
    "remove": "MAC removed",
    "remove_failed": "MAC remove failed",
    "bulk_add": "Bulk MAC addresses added",
    "bulk_failed": "Bulk add failed",
    "label_update": "Name updated",
    "label_update_failed": "Name update failed",
    "manual_backup": "Manual backup created",
    "manual_backup_failed": "Manual backup failed",
    "restore_backup": "Backup restored",
    "restore_failed": "Backup restore failed",
    "user_add": "User account created",
    "user_add_failed": "User account create failed",
    "user_password": "User password changed",
    "user_password_failed": "Password change failed",
    "self_password": "Own password changed",
    "self_password_failed": "Own password change failed",
    "user_toggle": "User account changed",
    "user_toggle_failed": "User account change failed",
    "user_role": "User role changed",
    "user_role_failed": "User role change failed",
    "access_denied": "Access denied",
}


SECURITY_LABELS = {
    "wpaeap": "WPA Enterprise",
    "wpapsk": "WPA Personal",
    "open": "Open",
    "wep": "WEP",
    "wpa2": "WPA2",
    "wpa3": "WPA3",
}

BACKUP_REASON_LABELS = {
    "manual": "Manual backup",
    "before-add": "Before adding MAC",
    "before-remove": "Before removing MAC",
    "before-bulk": "Before bulk add",
    "before-restore": "Before restore",
    "backup": "Backup",
}

ROLE_LABELS = {
    "admin": "Admin",
    "support": "Support",
}


def clean_role(raw: str | None) -> str:
    role = (raw or "support").strip().lower()
    if role not in ROLE_LABELS:
        raise ValueError("Role must be admin or support.")
    return role


def role_label(value: Any) -> str:
    role = str(value or "support").strip().lower()
    return ROLE_LABELS.get(role, "Support")


def action_label(value: Any) -> str:
    raw = str(value or "").strip()
    return ACTION_LABELS.get(raw, raw.replace("_", " ").strip().title() if raw else "")


def security_label(value: Any) -> str:
    raw = str(value or "").strip()
    key = raw.lower()
    if key in SECURITY_LABELS:
        return SECURITY_LABELS[key]
    return raw.upper() if raw else "Unknown"


def backup_reason_label(value: Any) -> str:
    raw = str(value or "").strip()
    return BACKUP_REASON_LABELS.get(raw, raw.replace("-", " ").replace("_", " ").strip().title() if raw else "Backup")


def detail_label(value: Any) -> str:
    detail = str(value or "").strip()
    replacements = {
        "Created dashboard user": "Created user account",
        "Changed dashboard user password": "Changed user password",
        "Set active=0": "Disabled user account",
        "Set active=1": "Enabled user account",
        "Changed user role to Admin": "Changed user role to Admin",
        "Changed user role to Support": "Changed user role to Support",
        "Updated local label for duplicate MAC": "Updated name for existing MAC",
        "Bulk enabled allow filtering": "Turned on MAC allow list",
    }
    if detail in replacements:
        return replacements[detail]
    return detail

def app_config() -> dict[str, Any]:
    return {
        "allow_enable_filtering": env_bool("ALLOW_ENABLE_FILTERING", True),
        "allow_disable_filtering": env_bool("ALLOW_DISABLE_FILTERING", False),
        "allow_deny_mode_edits": env_bool("ALLOW_DENY_MODE_EDITS", False),
        "allow_remove_last_mac": env_bool("ALLOW_REMOVE_LAST_MAC", False),
    }


def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__)
    app.config["APP_NAME"] = os.getenv("APP_NAME", "UniFi MAC Filtering")
    app.config["SECRET_KEY"] = os.getenv("APP_SECRET_KEY") or secrets.token_hex(32)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=int(os.getenv("SESSION_MINUTES", "60")))
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    app.config["DISPLAY_TIMEZONE"] = os.getenv("DASHBOARD_TIMEZONE", "Asia/Karachi")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.jinja_env.filters["display_datetime"] = display_datetime
    app.jinja_env.filters["action_label"] = action_label
    app.jinja_env.filters["detail_label"] = detail_label
    app.jinja_env.filters["backup_reason_label"] = backup_reason_label
    app.jinja_env.filters["role_label"] = role_label

    data_dir = Path(os.getenv("DATA_DIR", str(Path.cwd() / "instance")))
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "backups").mkdir(parents=True, exist_ok=True)
    app.config["DATA_DIR"] = data_dir
    app.config["DATABASE"] = str(data_dir / "dashboard.sqlite3")

    with app.app_context():
        init_db()
        bootstrap_env_user()

    @app.before_request
    def require_login() -> None | Response:
        if request.endpoint in {"login", "static", "health"}:
            return None
        if "user" not in session:
            return redirect(url_for("login"))
        return None

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return {
            "app_name": app.config["APP_NAME"],
            "current_user": session.get("user"),
            "current_user_role": session.get("role", "support"),
            "is_admin": session.get("role") == "admin",
            "csrf_token": token,
            "cfg": app_config(),
            "display_timezone": app.config["DISPLAY_TIMEZONE"],
        }

    @app.teardown_appcontext
    def close_db(_: BaseException | None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str | Response:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user_row = get_user(username)
            if user_row and bool(user_row["is_active"]) and check_password_hash(str(user_row["password_hash"]), password):
                db = get_db()
                db.execute("UPDATE dashboard_users SET last_login_at = ? WHERE username = ?", (now_iso(), username))
                db.commit()
                session.clear()
                session.permanent = True
                session["user"] = username
                session["role"] = str(user_row["role"] if "role" in user_row.keys() else "admin")
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("dashboard"))
            flash("Invalid username or password.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    def logout() -> Response:
        verify_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.route("/account", methods=["GET", "POST"])
    def account() -> str | Response:
        username = session["user"]
        user_row = get_user(username)
        if not user_row:
            session.clear()
            flash("Your account was not found. Sign in again.", "error")
            return redirect(url_for("login"))
        if request.method == "POST":
            verify_csrf()
            source_ip = client_ip()
            try:
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_password", "")
                if not check_password_hash(str(user_row["password_hash"]), current_password):
                    raise ValueError("Current password is incorrect.")
                if len(new_password) < 8:
                    raise ValueError("New password must be at least 8 characters.")
                if new_password != confirm_password:
                    raise ValueError("New passwords do not match.")
                set_dashboard_user_password(username, new_password, username)
                audit_system(username, source_ip, "self_password", username, "Changed own password", True)
                flash("Password changed.", "success")
                return redirect(url_for("account"))
            except Exception as exc:
                safe_audit(username, source_ip, "self_password_failed", "system", "", "", str(exc))
                flash(str(exc), "error")
        return render_template("account.html", row=user_row)

    @app.route("/")
    def dashboard() -> str:
        q = request.args.get("q", "").strip().lower()
        status = request.args.get("status", "").strip().lower()
        try:
            wlans = UniFiClient().list_wlans()
            rows = [wlan_summary(wlan) for wlan in wlans]
            if q:
                rows = [row for row in rows if q in row["name"].lower() or q in row["id"].lower()]
            if status == "on":
                rows = [row for row in rows if row["mac_filter_enabled"]]
            elif status == "off":
                rows = [row for row in rows if not row["mac_filter_enabled"]]
            rows.sort(key=lambda item: item["name"].lower())
            return render_template("dashboard.html", rows=rows, q=q, status=status)
        except UniFiError as exc:
            flash(str(exc), "error")
            return render_template("dashboard.html", rows=[], q=q, status=status)

    @app.route("/ssid/<ssid_id>")
    def ssid_detail(ssid_id: str) -> str | Response:
        try:
            wlan = UniFiClient().get_wlan(ssid_id)
        except UniFiError as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))
        return render_ssid(wlan)

    @app.route("/ssid/<ssid_id>/add", methods=["POST"])
    def add_mac(ssid_id: str) -> Response:
        verify_csrf()
        user = session["user"]
        source_ip = client_ip()
        raw_mac = request.form.get("mac", "")
        label = clean_label(request.form.get("label", ""))
        try:
            mac = normalize_mac(raw_mac)
            client = UniFiClient()
            wlan = client.get_wlan(ssid_id)
            ensure_editable_allow_mode(wlan)
            current = wlan_mac_list(wlan)
            if mac in current:
                if label:
                    upsert_mac_label(mac, label, user)
                    audit(user, source_ip, "label_update", wlan, mac, label, "Updated name for existing MAC", True)
                flash(f"{mac} is already on {wlan.get('name')}.", "info")
                return redirect(url_for("ssid_detail", ssid_id=ssid_id))
            backup_wlan(wlan, "before-add", created_by=user, source_ip=source_ip)
            wlan["mac_filter_list"] = sorted(set(current + [mac]))
            updated = client.update_wlan(ssid_id, wlan)
            if label:
                upsert_mac_label(mac, label, user)
            audit(user, source_ip, "add", updated, mac, label, "Added MAC address", True)
            flash(f"Added {mac} to {updated.get('name')}.", "success")
        except Exception as exc:
            safe_audit(user, source_ip, "add_failed", ssid_id, raw_mac, label, str(exc))
            flash(str(exc), "error")
        return redirect(url_for("ssid_detail", ssid_id=ssid_id))

    @app.route("/ssid/<ssid_id>/remove", methods=["POST"])
    def remove_mac(ssid_id: str) -> Response:
        verify_csrf()
        user = session["user"]
        source_ip = client_ip()
        raw_mac = request.form.get("mac", "")
        try:
            mac = normalize_mac(raw_mac)
            client = UniFiClient()
            wlan = client.get_wlan(ssid_id)
            ensure_editable_allow_mode(wlan)
            current = wlan_mac_list(wlan)
            if mac not in current:
                flash(f"{mac} is not on this allow list.", "info")
                return redirect(url_for("ssid_detail", ssid_id=ssid_id))
            if len(current) <= 1 and not app_config()["allow_remove_last_mac"]:
                raise ValueError("Refusing to remove the last allowed MAC while filtering is enabled.")
            backup_wlan(wlan, "before-remove", created_by=user, source_ip=source_ip)
            wlan["mac_filter_list"] = [item for item in current if item != mac]
            updated = client.update_wlan(ssid_id, wlan)
            label = get_mac_label(mac) or ""
            audit(user, source_ip, "remove", updated, mac, label, "Removed MAC address", True)
            flash(f"Removed {mac} from {updated.get('name')}.", "success")
        except Exception as exc:
            safe_audit(user, source_ip, "remove_failed", ssid_id, raw_mac, "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("ssid_detail", ssid_id=ssid_id))

    @app.route("/ssid/<ssid_id>/label", methods=["POST"])
    def update_label(ssid_id: str) -> Response:
        verify_csrf()
        user = session["user"]
        source_ip = client_ip()
        try:
            mac = normalize_mac(request.form.get("mac", ""))
            label = clean_label(request.form.get("label", ""))
            wlan = UniFiClient().get_wlan(ssid_id)
            if label:
                upsert_mac_label(mac, label, user)
                audit(user, source_ip, "label_update", wlan, mac, label, "Updated local MAC name", True)
            else:
                delete_mac_label(mac)
                audit(user, source_ip, "label_delete", wlan, mac, "", "Deleted local MAC name", True)
            flash(f"Updated local name for {mac}.", "success")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("ssid_detail", ssid_id=ssid_id))

    @app.route("/ssid/<ssid_id>/bulk-preview", methods=["POST"])
    def bulk_preview(ssid_id: str) -> str | Response:
        verify_csrf()
        try:
            wlan = UniFiClient().get_wlan(ssid_id)
            text = request.form.get("bulk_text", "")
            uploaded = request.files.get("bulk_file")
            if uploaded and uploaded.filename:
                file_text = uploaded.read().decode("utf-8-sig", errors="replace")
                text = f"{text}\n{file_text}" if text else file_text
            entries, invalids = parse_bulk_input(text)
            current = set(wlan_mac_list(wlan))
            seen: set[str] = set()
            preview: list[dict[str, Any]] = []
            for entry in entries:
                mac = entry["mac"]
                duplicate_input = mac in seen
                seen.add(mac)
                preview.append(
                    {
                        "mac": mac,
                        "label": entry.get("label", ""),
                        "raw": entry.get("raw", ""),
                        "exists": mac in current,
                        "duplicate_input": duplicate_input,
                    }
                )
            enable_if_disabled = request.form.get("enable_if_disabled") == "1"
            return render_template(
                "bulk_preview.html",
                wlan=wlan_summary(wlan),
                entries=preview,
                invalids=invalids,
                preview_json=json.dumps(preview),
                enable_if_disabled=enable_if_disabled,
                allow_apply=bool(preview),
            )
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("ssid_detail", ssid_id=ssid_id))

    @app.route("/ssid/<ssid_id>/bulk-apply", methods=["POST"])
    def bulk_apply(ssid_id: str) -> Response:
        verify_csrf()
        user = session["user"]
        source_ip = client_ip()
        try:
            preview = json.loads(request.form.get("preview_json", "[]"))
            enable_if_disabled = request.form.get("enable_if_disabled") == "1"
            client = UniFiClient()
            wlan = client.get_wlan(ssid_id)
            currently_enabled = bool(wlan.get("mac_filter_enabled"))
            policy = str(wlan.get("mac_filter_policy", "allow")).lower()

            if not currently_enabled:
                if not current_is_admin():
                    raise ValueError("MAC allow list is off. Ask an admin to turn it on first.")
                if not enable_if_disabled or not app_config()["allow_enable_filtering"]:
                    raise ValueError("MAC allow list is off. Use the enable checkbox to turn it on.")
                wlan["mac_filter_enabled"] = True
                wlan["mac_filter_policy"] = "allow"
                policy = "allow"
            elif policy != "allow":
                raise ValueError("This WiFi network is using deny mode. Editing is blocked in this dashboard.")

            current = wlan_mac_list(wlan)
            current_set = set(current)
            added: list[dict[str, str]] = []
            skipped = 0
            seen: set[str] = set()

            for item in preview:
                mac = normalize_mac(str(item.get("mac", "")))
                label = clean_label(str(item.get("label", "")))
                if mac in seen:
                    skipped += 1
                    continue
                seen.add(mac)
                if label:
                    upsert_mac_label(mac, label, user)
                if mac in current_set:
                    skipped += 1
                    continue
                current.append(mac)
                current_set.add(mac)
                added.append({"mac": mac, "label": label})

            if not current:
                raise ValueError("Refusing to enable an empty allow list.")

            if added or not currently_enabled:
                backup_wlan(wlan, "before-bulk", created_by=user, source_ip=source_ip)
                wlan["mac_filter_list"] = sorted(set(current))
                updated = client.update_wlan(ssid_id, wlan)
                for item in added:
                    audit(user, source_ip, "bulk_add", updated, item["mac"], item["label"], "Bulk added MAC address", True)
                if not currently_enabled:
                    audit(user, source_ip, "enable_allow_filter", updated, "", "", "Enabled allow-list MAC filtering", True)
                flash(f"Bulk apply complete. Added {len(added)} MAC(s), skipped {skipped} duplicate/existing row(s).", "success")
            else:
                flash(f"No UniFi changes needed. Skipped {skipped} duplicate/existing row(s). Labels were still updated locally.", "info")
        except Exception as exc:
            safe_audit(user, source_ip, "bulk_failed", ssid_id, "", "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("ssid_detail", ssid_id=ssid_id))

    @app.route("/audit")
    def audit_log() -> str:
        require_admin()
        filters = audit_filters_from_request()
        rows = query_audit(limit=500, filters=filters)
        users = list_usernames()
        actions = [{"value": item, "label": action_label(item)} for item in list_audit_actions()]
        return render_template("audit.html", rows=rows, filters=filters, users=users, actions=actions)

    @app.route("/audit.csv")
    def audit_csv() -> Response:
        require_admin()
        filters = audit_filters_from_request()
        rows = query_audit(limit=10000, filters=filters)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "user", "source_ip", "action", "wifi_name", "wifi_id", "mac", "name", "change_details", "status"])
        for row in rows:
            writer.writerow([
                row["created_at"],
                row["username"],
                row["source_ip"],
                action_label(row["action"]),
                row["ssid_name"],
                row["ssid_id"],
                row["mac"],
                row["label"],
                detail_label(row["detail"]),
                "Success" if row["success"] else "Failed",
            ])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=unifi-mac-filtering-audit.csv"})

    @app.route("/ssid/<ssid_id>/backup", methods=["POST"])
    def backup_now(ssid_id: str) -> Response:
        require_admin()
        verify_csrf()
        user = session["user"]
        source_ip = client_ip()
        try:
            client = UniFiClient()
            wlan = client.get_wlan(ssid_id)
            path = backup_wlan(wlan, "manual", created_by=user, source_ip=source_ip)
            audit(user, source_ip, "manual_backup", wlan, "", "", f"Created backup {path.name}", True)
            flash(f"Backup created for {wlan.get('name')}.", "success")
        except Exception as exc:
            safe_audit(user, source_ip, "manual_backup_failed", ssid_id, "", "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("ssid_detail", ssid_id=ssid_id))

    @app.route("/backups")
    def backups() -> str:
        require_admin()
        rows = list_backups()
        q = request.args.get("q", "").strip().lower()
        if q:
            rows = [row for row in rows if q in row["filename"].lower() or q in row["ssid_name"].lower() or q in row["ssid_id"].lower() or q in row["reason"].lower()]
        return render_template("backups.html", rows=rows, q=q)

    @app.route("/backups/download/<path:filename>")
    def backup_download(filename: str) -> Response:
        require_admin()
        path = safe_backup_path(filename)
        return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/json")

    @app.route("/backups/restore/<path:filename>", methods=["POST"])
    def backup_restore(filename: str) -> Response:
        require_admin()
        verify_csrf()
        user = session["user"]
        source_ip = client_ip()
        try:
            path = safe_backup_path(filename)
            payload = json.loads(path.read_text(encoding="utf-8"))
            backup = extract_wlan_from_backup(payload)
            ssid_id = str(backup.get("_id", ""))
            if not ssid_id:
                raise ValueError("Backup file does not contain a WiFi network ID.")
            client = UniFiClient()
            current_wlan = client.get_wlan(ssid_id)
            backup_wlan(current_wlan, "before-restore", created_by=user, source_ip=source_ip)
            updated = client.update_wlan(ssid_id, backup)
            audit(user, source_ip, "restore_backup", updated, "", "", f"Restored backup {path.name}", True)
            flash(f"Restored backup for {updated.get('name')}.", "success")
        except Exception as exc:
            safe_audit(user, source_ip, "restore_failed", filename, "", "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("backups"))

    @app.route("/users")
    def users() -> str:
        require_admin()
        return render_template("users.html", rows=list_users())

    @app.route("/users/add", methods=["POST"])
    def user_add() -> Response:
        require_admin()
        verify_csrf()
        actor = session["user"]
        source_ip = client_ip()
        try:
            username = clean_username(request.form.get("username"))
            password = request.form.get("new_password") or request.form.get("password", "")
            display_name = clean_label(request.form.get("display_name", ""))
            role = clean_role(request.form.get("role", "support"))
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters.")
            create_dashboard_user(username, password, display_name, role, actor)
            audit_system(actor, source_ip, "user_add", username, f"Created {role_label(role).lower()} user account", True)
            flash(f"Created user {username}.", "success")
        except Exception as exc:
            safe_audit(actor, source_ip, "user_add_failed", "system", "", "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("users"))

    @app.route("/users/<username>/password", methods=["POST"])
    def user_password(username: str) -> Response:
        require_admin()
        verify_csrf()
        actor = session["user"]
        source_ip = client_ip()
        try:
            username = clean_username(username)
            password = request.form.get("new_password") or request.form.get("password", "")
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters.")
            set_dashboard_user_password(username, password, actor)
            audit_system(actor, source_ip, "user_password", username, "Changed user password", True)
            flash(f"Updated password for {username}.", "success")
        except Exception as exc:
            safe_audit(actor, source_ip, "user_password_failed", "system", "", "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("users"))

    @app.route("/users/<username>/role", methods=["POST"])
    def user_role(username: str) -> Response:
        require_admin()
        verify_csrf()
        actor = session["user"]
        source_ip = client_ip()
        try:
            username = clean_username(username)
            role = clean_role(request.form.get("role", "support"))
            set_dashboard_user_role(username, role, actor)
            audit_system(actor, source_ip, "user_role", username, f"Changed user role to {role_label(role)}", True)
            flash(f"Updated role for {username}.", "success")
        except Exception as exc:
            safe_audit(actor, source_ip, "user_role_failed", "system", "", "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("users"))

    @app.route("/users/<username>/toggle", methods=["POST"])
    def user_toggle(username: str) -> Response:
        require_admin()
        verify_csrf()
        actor = session["user"]
        source_ip = client_ip()
        try:
            username = clean_username(username)
            if username == actor:
                raise ValueError("You cannot disable your own account while logged in.")
            new_state = toggle_dashboard_user(username, actor)
            audit_system(actor, source_ip, "user_toggle", username, "Enabled user account" if new_state else "Disabled user account", True)
            flash(f"Updated {username}.", "success")
        except Exception as exc:
            safe_audit(actor, source_ip, "user_toggle_failed", "system", "", "", str(exc))
            flash(str(exc), "error")
        return redirect(url_for("users"))

    @app.errorhandler(PermissionError)
    def handle_permission_error(exc: PermissionError) -> Response:
        flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.route("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": app.config["APP_NAME"]}

    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        g.db = db
    return g.db


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS mac_labels (
            mac TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            username TEXT NOT NULL,
            source_ip TEXT NOT NULL,
            action TEXT NOT NULL,
            ssid_name TEXT NOT NULL,
            ssid_id TEXT NOT NULL,
            mac TEXT NOT NULL,
            label TEXT NOT NULL,
            detail TEXT NOT NULL,
            success INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dashboard_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'support',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL DEFAULT 'system',
            created_at TEXT NOT NULL,
            updated_by TEXT NOT NULL DEFAULT 'system',
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        );
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(dashboard_users)").fetchall()}
    if "role" not in columns:
        db.execute("ALTER TABLE dashboard_users ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
        db.execute("UPDATE dashboard_users SET role = 'admin' WHERE role IS NULL OR role = ''")
    db.commit()


def bootstrap_env_user() -> None:
    """Create the first dashboard user from APP_USERNAME/APP_PASSWORD_HASH if the users table is empty."""
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS c FROM dashboard_users").fetchone()["c"]
    if count:
        return
    username = os.getenv("APP_USERNAME", "helpdesk").strip() or "helpdesk"
    password_hash = os.getenv("APP_PASSWORD_HASH", "").strip()
    if not password_hash or password_hash.startswith("replace_with"):
        return
    stamp = now_iso()
    db.execute(
        """
        INSERT INTO dashboard_users (username, password_hash, display_name, role, is_active, created_by, created_at, updated_by, updated_at)
        VALUES (?, ?, ?, 'admin', 1, 'env', ?, 'env', ?)
        """,
        (username, password_hash, username, stamp, stamp),
    )
    db.commit()


def verify_csrf() -> None:
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token")
    if not sent or not expected or not secrets.compare_digest(sent, expected):
        raise ValueError("Invalid CSRF token. Refresh the page and try again.")


def client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


def current_role() -> str:
    return str(session.get("role", "support"))


def current_is_admin() -> bool:
    return current_role() == "admin"


def require_admin() -> None:
    if not current_is_admin():
        raise PermissionError("Admin access is required for this action.")


def deny_to_dashboard(message: str = "Admin access is required for this page.") -> Response:
    flash(message, "error")
    return redirect(url_for("dashboard"))


def wlan_mac_list(wlan: dict[str, Any]) -> list[str]:
    raw = wlan.get("mac_filter_list") or []
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        try:
            result.append(normalize_mac(str(item)))
        except ValueError:
            continue
    return sorted(set(result))


def wlan_summary(wlan: dict[str, Any]) -> dict[str, Any]:
    macs = wlan_mac_list(wlan)
    enabled = bool(wlan.get("mac_filter_enabled"))
    policy = str(wlan.get("mac_filter_policy", "allow")).lower()
    return {
        "id": wlan.get("_id", ""),
        "name": wlan.get("name", "Unnamed WiFi network"),
        "enabled": bool(wlan.get("enabled")),
        "security": security_label(wlan.get("security", "")),
        "band": wlan.get("wlan_band") or ", ".join(wlan.get("wlan_bands", []) if isinstance(wlan.get("wlan_bands"), list) else []),
        "mac_filter_enabled": enabled,
        "mac_filter_policy": policy,
        "mac_count": len(macs),
        "status": "Off" if not enabled else "On",
        "policy_label": policy.upper() if enabled else "None",
    }


def render_ssid(wlan: dict[str, Any]) -> str:
    macs = wlan_mac_list(wlan)
    labels = get_mac_labels(macs)
    rows = [{"mac": mac, "label": labels.get(mac, "")} for mac in macs]
    return render_template("ssid.html", wlan=wlan_summary(wlan), rows=rows)


def ensure_editable_allow_mode(wlan: dict[str, Any]) -> None:
    if not bool(wlan.get("mac_filter_enabled")):
        raise ValueError("MAC allow list is off. Use Add many MAC addresses with the enable checkbox to turn it on safely.")
    policy = str(wlan.get("mac_filter_policy", "allow")).lower()
    if policy != "allow":
        if not app_config()["allow_deny_mode_edits"]:
            raise ValueError("This WiFi network is using deny mode. Editing is blocked in this dashboard.")


def backup_wlan(wlan: dict[str, Any], reason: str, created_by: str = "system", source_ip: str = "") -> Path:
    data_dir: Path = current_app.config["DATA_DIR"]
    ssid = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(wlan.get("name", "ssid"))).strip("-") or "ssid"
    wlan_id = str(wlan.get("_id", "unknown"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = data_dir / "backups" / f"{stamp}-{ssid}-{wlan_id}-{reason}.json"
    wrapper = {
        "_dashboard_backup_meta": {
            "created_at": now_iso(),
            "created_by": created_by,
            "source_ip": source_ip,
            "reason": reason,
            "ssid_name": str(wlan.get("name", "")),
            "ssid_id": wlan_id,
        },
        "wlan": wlan,
    }
    # Backward-compatible restore still accepts raw WiFi settings JSON, but new backups keep metadata beside it.
    path.write_text(json.dumps(wrapper, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def upsert_mac_label(mac: str, label: str, username: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO mac_labels (mac, label, updated_by, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(mac) DO UPDATE SET
            label=excluded.label,
            updated_by=excluded.updated_by,
            updated_at=excluded.updated_at
        """,
        (mac, label, username, now_iso()),
    )
    db.commit()


def delete_mac_label(mac: str) -> None:
    db = get_db()
    db.execute("DELETE FROM mac_labels WHERE mac = ?", (mac,))
    db.commit()


def get_mac_label(mac: str) -> str | None:
    db = get_db()
    row = db.execute("SELECT label FROM mac_labels WHERE mac = ?", (mac,)).fetchone()
    return str(row["label"]) if row else None


def get_mac_labels(macs: list[str]) -> dict[str, str]:
    if not macs:
        return {}
    placeholders = ",".join("?" for _ in macs)
    db = get_db()
    rows = db.execute(f"SELECT mac, label FROM mac_labels WHERE mac IN ({placeholders})", macs).fetchall()
    return {str(row["mac"]): str(row["label"]) for row in rows}


def audit(username: str, source_ip: str, action: str, wlan: dict[str, Any], mac: str, label: str, detail: str, success: bool) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO audit_log
        (created_at, username, source_ip, action, ssid_name, ssid_id, mac, label, detail, success)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            username,
            source_ip,
            action,
            str(wlan.get("name", "")),
            str(wlan.get("_id", "")),
            mac,
            label,
            detail[:500],
            1 if success else 0,
        ),
    )
    db.commit()


def audit_system(username: str, source_ip: str, action: str, target: str, detail: str, success: bool) -> None:
    audit(username, source_ip, action, {"name": "System", "_id": "system"}, target, "", detail, success)


def safe_audit(username: str, source_ip: str, action: str, ssid_id: str, mac: str, label: str, detail: str) -> None:
    try:
        audit(username, source_ip, action, {"name": ssid_id, "_id": ssid_id}, mac, label, detail, False)
    except Exception:
        pass


def audit_filters_from_request() -> dict[str, str]:
    return {
        "q": request.args.get("q", "").strip(),
        "user": request.args.get("user", "").strip(),
        "action": request.args.get("action", "").strip(),
        "success": request.args.get("success", "").strip(),
    }


def query_audit(limit: int = 250, filters: dict[str, str] | None = None) -> list[sqlite3.Row]:
    filters = filters or {}
    db = get_db()
    clauses: list[str] = []
    params: list[Any] = []
    q = filters.get("q", "").strip().lower()
    if q:
        clauses.append("(LOWER(ssid_name) LIKE ? OR LOWER(ssid_id) LIKE ? OR LOWER(mac) LIKE ? OR LOWER(label) LIKE ? OR LOWER(detail) LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like, like])
    if filters.get("user"):
        clauses.append("username = ?")
        params.append(filters["user"])
    if filters.get("action"):
        clauses.append("action = ?")
        params.append(filters["action"])
    if filters.get("success") in {"0", "1"}:
        clauses.append("success = ?")
        params.append(int(filters["success"]))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)
    return list(db.execute(f"SELECT * FROM audit_log{where} ORDER BY id DESC LIMIT ?", params).fetchall())


def list_audit_actions() -> list[str]:
    db = get_db()
    return [str(row["action"]) for row in db.execute("SELECT DISTINCT action FROM audit_log ORDER BY action").fetchall()]


def parse_bulk_input(text: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    entries: list[dict[str, str]] = []
    invalids: list[dict[str, str]] = []
    text = text or ""
    lines = [line.rstrip("\r") for line in text.splitlines()]
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return [], []

    sample = "\n".join(nonempty[:5])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(nonempty, dialect))
    header = [cell.strip().lower() for cell in rows[0]] if rows else []
    if "mac" in header or "mac address" in header:
        mac_idx = header.index("mac") if "mac" in header else header.index("mac address")
        label_idx = next((idx for idx, name in enumerate(header) if name in {"name", "owner", "description", "label", "user", "asset"}), None)
        for row_num, row in enumerate(rows[1:], start=2):
            raw_line = nonempty[row_num - 1]
            if mac_idx >= len(row) or not row[mac_idx].strip():
                invalids.append({"line": str(row_num), "raw": raw_line, "error": "Missing MAC"})
                continue
            try:
                mac = normalize_mac(row[mac_idx])
                label = clean_label(row[label_idx]) if label_idx is not None and label_idx < len(row) else ""
                entries.append({"mac": mac, "label": label, "raw": raw_line})
            except ValueError as exc:
                invalids.append({"line": str(row_num), "raw": raw_line, "error": str(exc)})
        return entries, invalids

    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        matches = list(MAC_PATTERN.finditer(stripped))
        if not matches:
            invalids.append({"line": str(line_num), "raw": stripped, "error": "No MAC address found"})
            continue
        for idx, match in enumerate(matches):
            try:
                mac = normalize_mac(match.group(0))
            except ValueError as exc:
                invalids.append({"line": str(line_num), "raw": stripped, "error": str(exc)})
                continue
            label = ""
            if len(matches) == 1:
                label = stripped[: match.start()] + " " + stripped[match.end() :]
                label = clean_label(label.strip(" ,-;\t"))
            entries.append({"mac": mac, "label": label, "raw": stripped})
    return entries, invalids


# User management

def get_user(username: str) -> sqlite3.Row | None:
    db = get_db()
    return db.execute("SELECT * FROM dashboard_users WHERE username = ?", (username,)).fetchone()


def list_users() -> list[sqlite3.Row]:
    db = get_db()
    return list(db.execute("SELECT * FROM dashboard_users ORDER BY username").fetchall())


def list_usernames() -> list[str]:
    db = get_db()
    return [str(row["username"]) for row in db.execute("SELECT username FROM dashboard_users ORDER BY username").fetchall()]


def create_dashboard_user(username: str, password: str, display_name: str, role: str, actor: str) -> None:
    db = get_db()
    if get_user(username):
        raise ValueError("That username already exists.")
    stamp = now_iso()
    db.execute(
        """
        INSERT INTO dashboard_users (username, password_hash, display_name, role, is_active, created_by, created_at, updated_by, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (username, generate_password_hash(password), display_name, role, actor, stamp, actor, stamp),
    )
    db.commit()


def set_dashboard_user_password(username: str, password: str, actor: str) -> None:
    db = get_db()
    if not get_user(username):
        raise ValueError("User not found.")
    db.execute(
        "UPDATE dashboard_users SET password_hash = ?, updated_by = ?, updated_at = ? WHERE username = ?",
        (generate_password_hash(password), actor, now_iso(), username),
    )
    db.commit()


def active_admin_count(exclude_username: str | None = None) -> int:
    db = get_db()
    if exclude_username:
        row = db.execute("SELECT COUNT(*) AS c FROM dashboard_users WHERE is_active = 1 AND role = 'admin' AND username != ?", (exclude_username,)).fetchone()
    else:
        row = db.execute("SELECT COUNT(*) AS c FROM dashboard_users WHERE is_active = 1 AND role = 'admin'").fetchone()
    return int(row["c"])


def set_dashboard_user_role(username: str, role: str, actor: str) -> None:
    db = get_db()
    row = get_user(username)
    if not row:
        raise ValueError("User not found.")
    if username == actor and role != "admin":
        raise ValueError("You cannot change your own role from admin while logged in.")
    if str(row["role"]) == "admin" and role != "admin" and int(row["is_active"]) == 1 and active_admin_count(exclude_username=username) < 1:
        raise ValueError("Cannot remove the last active admin account.")
    db.execute("UPDATE dashboard_users SET role = ?, updated_by = ?, updated_at = ? WHERE username = ?", (role, actor, now_iso(), username))
    db.commit()


def toggle_dashboard_user(username: str, actor: str) -> int:
    db = get_db()
    row = get_user(username)
    if not row:
        raise ValueError("User not found.")
    if int(row["is_active"]) == 1:
        active_count = db.execute("SELECT COUNT(*) AS c FROM dashboard_users WHERE is_active = 1").fetchone()["c"]
        if active_count <= 1:
            raise ValueError("Cannot disable the last active user.")
        if str(row["role"]) == "admin" and active_admin_count(exclude_username=username) < 1:
            raise ValueError("Cannot disable the last active admin account.")
    new_state = 0 if int(row["is_active"]) else 1
    db.execute("UPDATE dashboard_users SET is_active = ?, updated_by = ?, updated_at = ? WHERE username = ?", (new_state, actor, now_iso(), username))
    db.commit()
    return new_state


# Backups

def backup_dir() -> Path:
    return Path(current_app.config["DATA_DIR"]) / "backups"


def safe_backup_path(filename: str) -> Path:
    name = Path(filename).name
    path = (backup_dir() / name).resolve()
    base = backup_dir().resolve()
    if base not in path.parents or not path.is_file() or path.suffix.lower() != ".json":
        raise ValueError("Backup file not found.")
    return path


def extract_wlan_from_backup(payload: dict[str, Any]) -> dict[str, Any]:
    wlan = payload.get("wlan") if isinstance(payload.get("wlan"), dict) else payload
    if not isinstance(wlan, dict):
        raise ValueError("Invalid backup content.")
    return wlan


def list_backups() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(backup_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            meta = payload.get("_dashboard_backup_meta", {}) if isinstance(payload, dict) else {}
            wlan = extract_wlan_from_backup(payload) if isinstance(payload, dict) else {}
            ssid_name = str(meta.get("ssid_name") or wlan.get("name") or "")
            ssid_id = str(meta.get("ssid_id") or wlan.get("_id") or "")
            reason = str(meta.get("reason") or filename_reason(path.name))
            created_by = str(meta.get("created_by") or "")
            created_at = str(meta.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"))
        except Exception:
            ssid_name = "Unreadable backup"
            ssid_id = ""
            reason = filename_reason(path.name)
            created_by = ""
            created_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        rows.append(
            {
                "filename": path.name,
                "created_at": created_at,
                "ssid_name": ssid_name,
                "ssid_id": ssid_id,
                "reason": reason,
                "created_by": created_by,
                "size": path.stat().st_size,
            }
        )
    return rows


def filename_reason(filename: str) -> str:
    stem = filename[:-5] if filename.endswith(".json") else filename
    parts = stem.split("-")
    if len(parts) >= 4:
        return parts[-1]
    return "backup"
