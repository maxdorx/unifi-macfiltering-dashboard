#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

import sys
sys.path.insert(0, str(ROOT))

from unifi_client import UniFiClient  # noqa: E402


def main() -> None:
    client = UniFiClient()
    wlans = client.list_wlans()
    print(f"UniFi login OK. Site={os.getenv('UNIFI_SITE', 'default')}. WiFi networks found: {len(wlans)}")
    for wlan in wlans:
        name = wlan.get("name", "Unnamed")
        wlan_id = wlan.get("_id", "")
        enabled = wlan.get("enabled")
        mac_enabled = wlan.get("mac_filter_enabled")
        policy = wlan.get("mac_filter_policy")
        mac_count = len(wlan.get("mac_filter_list") or [])
        print(f"- {name} | id={wlan_id} | enabled={enabled} | mac_filter_enabled={mac_enabled} | policy={policy} | mac_count={mac_count}")


if __name__ == "__main__":
    main()
