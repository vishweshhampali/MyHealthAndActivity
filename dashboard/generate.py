"""Render the training-log dashboard from the Notion Activity Log.

Reads NOTION_API_TOKEN and NOTION_DATABASE_ID from the environment, pulls every
row of the Activity Log, and writes a self-contained HTML file with the data
baked in. No secrets end up in the output — only the numbers.
"""

import json
import os
from datetime import datetime, timezone

import requests

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

TOKEN = os.environ["NOTION_API_TOKEN"]
DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.html")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "site")


def _headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_rows() -> list[dict]:
    """Page through the whole database. Notion caps each response at 100 rows."""
    rows, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        resp = requests.post(
            f"{NOTION_API}/databases/{DATABASE_ID}/query",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        if not resp.ok:
            print(f"Notion API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        body = resp.json()
        rows.extend(body.get("results", []))
        if not body.get("has_more"):
            break
        cursor = body.get("next_cursor")
    return rows


def _num(props: dict, name: str):
    prop = props.get(name) or {}
    return prop.get("number")


def _date(props: dict, name: str):
    prop = props.get(name) or {}
    date_obj = prop.get("date") or {}
    return date_obj.get("start")


def _title(props: dict, name: str):
    prop = props.get(name) or {}
    parts = prop.get("title") or []
    return parts[0]["plain_text"] if parts else None


def parse(pages: list[dict]) -> list[dict]:
    out = []
    for page in pages:
        props = page.get("properties", {})
        # prefer the real Date property; fall back to the title text
        day = _date(props, "Date (property)") or _title(props, "Date")
        if not day:
            continue
        checkbox = (props.get("Trained Today") or {}).get("checkbox", False)
        out.append({
            "d": day[:10],
            "trained": "__YES__" if checkbox else "__NO__",
            "streak": _num(props, "Current Streak") or 0,
            "days_since": _num(props, "Days Since Last Session"),
            "week_days": _num(props, "Deliberate Days This Week") or 0,
            "running": _num(props, "Running Minutes") or 0,
            "walking": _num(props, "Walking Minutes") or 0,
            "gym": _num(props, "Gym Minutes") or 0,
            "sports": _num(props, "Sports Minutes") or 0,
            "total_min": _num(props, "Total Active Minutes") or 0,
            "distance": _num(props, "Distance Km") or 0,
            "sessions": _num(props, "Exercise Sessions") or 0,
            "min7": _num(props, "Minutes Last 7d") or 0,
            "min28": _num(props, "Minutes Last 28d") or 0,
            "acwr": _num(props, "ACWR Ratio"),
        })
    # newest first — the template reverses this itself
    out.sort(key=lambda r: r["d"], reverse=True)
    return out


def main():
    pages = fetch_rows()
    rows = parse(pages)
    if not rows:
        raise SystemExit("No rows returned from Notion — refusing to publish an empty dashboard.")

    # the template's RAW array has no `sessions` key; it comes via the lookup
    raw = [{k: v for k, v in r.items() if k != "sessions"} for r in rows]
    sessions = {r["d"]: r["sessions"] for r in rows if r["d"] >= "2026-07-01"}

    html = open(TEMPLATE_PATH, encoding="utf-8").read()
    html = html.replace("/*__RAW__*/[]", json.dumps(raw, separators=(",", ":")))
    html = html.replace("/*__SESSIONS__*/{}", json.dumps(sessions, separators=(",", ":")))
    html = html.replace(
        "__GENERATED_AT__",
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"wrote {out_path} — {len(rows)} rows, latest {rows[0]['d']}")


if __name__ == "__main__":
    main()
