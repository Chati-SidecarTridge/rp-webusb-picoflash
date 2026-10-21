#!/usr/bin/env python3
"""Check devices.json before opening a PR.

Usage: python3 tools/check-devices.py [path/to/devices.json] [--offline]

Checks that the file parses, every firmware has the fields the page uses,
ids are unique, device_type is RP2040 or RP2350, datetime is a real ISO 8601
date, and (unless --offline) every uf2_url answers. Exits 1 on any problem.
"""
import json
import sys
import urllib.request
from datetime import datetime

FIELDS = ("id", "name", "description", "device_type", "datetime", "version", "uf2_url", "post_install_html")


def url_ok(url):
    # A one-byte range GET: some hosts refuse HEAD or plain Python user agents.
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": "curl/8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 206), r.status
    except Exception as e:  # noqa: BLE001
        return False, getattr(e, "code", str(e))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    offline = "--offline" in sys.argv
    path = args[0] if args else "devices.json"
    problems = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"FAIL {path}: {e}")
        return 1

    seen = set()
    families = data.get("families")
    if not isinstance(families, list) or not families:
        problems.append("top level must be {\"families\": [...]} with at least one family")
        families = []
    for fam in families:
        fid = fam.get("id", "?")
        for key in ("id", "name", "firmwares"):
            if key not in fam:
                problems.append(f"family {fid}: missing {key}")
        for key in ("id",):
            if fid in seen:
                problems.append(f"duplicate id {fid}")
            seen.add(fid)
        for fw in fam.get("firmwares", []):
            wid = fw.get("id", "?")
            for key in FIELDS:
                if key not in fw:
                    problems.append(f"{fid}/{wid}: missing {key}")
            if wid in seen:
                problems.append(f"duplicate id {wid}")
            seen.add(wid)
            if fw.get("device_type") not in ("RP2040", "RP2350"):
                problems.append(f"{fid}/{wid}: device_type {fw.get('device_type')!r} is not RP2040 or RP2350")
            try:
                datetime.fromisoformat(str(fw.get("datetime", "")).replace("Z", "+00:00"))
            except ValueError:
                problems.append(f"{fid}/{wid}: datetime {fw.get('datetime')!r} is not a valid date")
            url = fw.get("uf2_url", "")
            if not url.startswith("https://"):
                problems.append(f"{fid}/{wid}: uf2_url is not https")
            elif not offline:
                ok, status = url_ok(url)
                print(f"{'ok  ' if ok else 'FAIL'} {status} {url}")
                if not ok:
                    problems.append(f"{fid}/{wid}: {url} answers {status}")

    for p in problems:
        print("PROBLEM", p)
    print(f"{len(seen)} ids checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
