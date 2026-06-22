from __future__ import annotations

import copy
import os
from typing import Any

import requests
from requests import Session
from requests.packages.urllib3.exceptions import InsecureRequestWarning


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class UniFiError(RuntimeError):
    pass


class UniFiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("UNIFI_BASE_URL", "https://127.0.0.1:8443").rstrip("/")
        self.site = os.getenv("UNIFI_SITE", "default").strip() or "default"
        self.username = os.getenv("UNIFI_USERNAME", "")
        self.password = os.getenv("UNIFI_PASSWORD", "")
        self.verify_ssl = env_bool("UNIFI_VERIFY_SSL", False)
        self.timeout = 20

        if not self.verify_ssl:
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

        if not self.username or not self.password:
            raise UniFiError("UNIFI_USERNAME and UNIFI_PASSWORD must be set")

    def _session(self) -> Session:
        session = requests.Session()
        session.verify = self.verify_ssl
        login_url = f"{self.base_url}/api/login"
        response = session.post(
            login_url,
            json={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        self._raise_for_unifi(response, "login")
        return session

    def _raise_for_unifi(self, response: requests.Response, action: str) -> None:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if not response.ok:
            raise UniFiError(f"UniFi {action} failed: HTTP {response.status_code} {response.text[:300]}")

        if isinstance(payload, dict) and payload.get("meta", {}).get("rc") not in (None, "ok"):
            msg = payload.get("meta", {}).get("msg") or payload.get("meta", {})
            raise UniFiError(f"UniFi {action} failed: {msg}")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/s/{self.site}{path}"

    def list_wlans(self) -> list[dict[str, Any]]:
        with self._session() as session:
            response = session.get(self._url("/rest/wlanconf"), timeout=self.timeout)
            self._raise_for_unifi(response, "list WiFi networks")
            data = response.json().get("data", [])
            return data if isinstance(data, list) else []

    def get_wlan(self, wlan_id: str) -> dict[str, Any]:
        with self._session() as session:
            response = session.get(self._url(f"/rest/wlanconf/{wlan_id}"), timeout=self.timeout)
            self._raise_for_unifi(response, "get WiFi network")
            data = response.json().get("data", [])
            if not data:
                raise UniFiError("WiFi network not found")
            return data[0]

    def update_wlan(self, wlan_id: str, wlan_object: dict[str, Any]) -> dict[str, Any]:
        body = copy.deepcopy(wlan_object)
        with self._session() as session:
            response = session.put(self._url(f"/rest/wlanconf/{wlan_id}"), json=body, timeout=self.timeout)
            self._raise_for_unifi(response, "update WiFi network")
            data = response.json().get("data", [])
            if not data:
                raise UniFiError("UniFi returned no updated WiFi data")
            return data[0]


SENSITIVE_KEYS = {
    "x_passphrase",
    "passphrase",
    "wep_key",
    "radius_secret",
    "radius_auth_secret",
    "radius_acct_secret",
    "private_key",
    "secret",
}


def redacted(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS or "passphrase" in key.lower() or "password" in key.lower() or "secret" in key.lower():
                safe[key] = "[REDACTED]"
            else:
                safe[key] = redacted(item)
        return safe
    if isinstance(value, list):
        return [redacted(item) for item in value]
    return value
