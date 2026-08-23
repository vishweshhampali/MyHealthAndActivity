"""Build the verbatim NDJSON representation of data points, in memory."""
import json
from datetime import datetime, timezone


def build_ndjson(data_type, method, points, point_time_fn):
    """Encode points as newline-delimited JSON bytes, ready for a BigQuery load job."""
    now = datetime.now(timezone.utc).isoformat()
    lines = []
    for p in points:
        lines.append(json.dumps({
            "data_type": data_type,
            "method": method,
            "point_time": point_time_fn(data_type, p),
            "ingested_at": now,
            "payload": p,          # verbatim ghealth --raw object
        }))
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
