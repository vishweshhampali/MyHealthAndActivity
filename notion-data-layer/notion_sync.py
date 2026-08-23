import requests

NOTION_VERSION = "2022-06-28"
NOTION_API = "https://api.notion.com/v1"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _find_existing_page(token: str, database_id: str, date_str: str) -> str | None:
    resp = requests.post(
        f"{NOTION_API}/databases/{database_id}/query",
        headers=_headers(token),
        json={"filter": {"property": "Date", "date": {"equals": date_str}}},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None


def _build_properties(row: dict, date_str: str) -> dict:
    def num(key):
        val = row.get(key)
        return {"number": float(val) if val is not None else None}

    return {
        "Date": {
            "title": [{"text": {"content": date_str}}],
        },
        "Trained Today": {"checkbox": bool(row["trained_today"])},
        "Current Streak": num("current_streak_days"),
        "Days Since Last Session": num("days_since_last_session"),
        "Deliberate Days This Week": num("deliberate_days_this_week"),
        "Running Minutes": num("running_minutes"),
        "Walking Minutes": num("walking_minutes"),
        "Gym Minutes": num("gym_minutes"),
        "Sports Minutes": num("sports_minutes"),
        "Total Active Minutes": num("total_active_minutes"),
        "Distance Km": num("distance_km"),
        "Exercise Sessions": num("exercise_session_count"),
        "Minutes Last 7d": num("minutes_last_7d"),
        "Minutes Last 28d": num("minutes_last_28d"),
        "ACWR Ratio": num("acwr_ratio"),
    }


def upsert_day(token: str, database_id: str, row: dict):
    date_str = row["activity_date"].isoformat()
    properties = _build_properties(row, date_str)
    existing_id = _find_existing_page(token, database_id, date_str)

    if existing_id:
        resp = requests.patch(
            f"{NOTION_API}/pages/{existing_id}",
            headers=_headers(token),
            json={"properties": properties},
            timeout=15,
        )
    else:
        resp = requests.post(
            f"{NOTION_API}/pages",
            headers=_headers(token),
            json={"parent": {"database_id": database_id}, "properties": properties},
            timeout=15,
        )
    resp.raise_for_status()
    return resp.json()
