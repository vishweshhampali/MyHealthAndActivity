"""Build the verbatim NDJSON representation of data points, in memory."""
import json
from datetime import datetime, timezone


def build_ndjson(data_type, method, points, point_time_fn, run_id=None):
    """Encode points as newline-delimited JSON bytes, ready for a BigQuery load job.

    run_id links each row back to the pipeline run that wrote it (raw._pipeline_runs)
    so a suspicious row can be traced straight to its run's status/error/log link.
    """
    now = datetime.now(timezone.utc).isoformat()
    lines = []
    for p in points:
        lines.append(json.dumps({
            "data_type": data_type,
            "method": method,
            "point_time": point_time_fn(data_type, p),
            "ingested_at": now,
            "run_id": run_id,
            "payload": p,          # verbatim ghealth --raw object
        }))
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
