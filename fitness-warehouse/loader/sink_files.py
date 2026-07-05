"""Write verbatim data points to local NDJSON files; resume from existing files."""
import json
import os
from datetime import date, datetime, timezone


def write_chunk(out_dir, data_type, method, c0, c1, points, point_time_fn):
    """Write one NDJSON file per (type, chunk). Each line wraps the verbatim payload."""
    d = os.path.join(out_dir, data_type)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{method}_{c0.isoformat()}_{c1.isoformat()}.ndjson")
    now = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        for p in points:
            f.write(json.dumps({
                "data_type": data_type,
                "method": method,
                "point_time": point_time_fn(data_type, p),
                "ingested_at": now,
                "payload": p,          # verbatim ghealth --raw object
            }) + "\n")
    return path, len(points)


def last_chunk_end(out_dir, data_type):
    """Latest chunk end-date already on disk for this type, for resuming forward."""
    d = os.path.join(out_dir, data_type)
    if not os.path.isdir(d):
        return None
    ends = []
    for fn in os.listdir(d):
        try:
            ends.append(date.fromisoformat(fn.rsplit("_", 1)[1].replace(".ndjson", "")))
        except Exception:
            pass
    return max(ends) if ends else None


def first_chunk_start(out_dir, data_type):
    """Earliest chunk start-date already on disk for this type, for backfilling further back."""
    d = os.path.join(out_dir, data_type)
    if not os.path.isdir(d):
        return None
    starts = []
    for fn in os.listdir(d):
        try:
            starts.append(date.fromisoformat(fn.split("_")[-2]))
        except Exception:
            pass
    return min(starts) if starts else None
