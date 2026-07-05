"""Thin wrapper over the ghealth CLI: run commands with --raw, paginate, chunk dates."""
import json
import subprocess
from datetime import date, timedelta

from tenacity import retry, wait_exponential, stop_after_attempt


def _run(args: list[str]) -> dict:
    """Run `ghealth <args> --raw --format json` and return the parsed response."""
    cmd = ["ghealth", *args, "--raw", "--format", "json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 2:
        raise RuntimeError("ghealth auth error — run `ghealth auth login`")
    if r.returncode != 0:
        raise RuntimeError(f"ghealth {' '.join(args)} exit {r.returncode}: {r.stderr.strip()}")
    return json.loads(r.stdout or '{"dataPoints": []}')


def chunks(start: date, end: date, days: int):
    """Yield (chunk_start, chunk_end) inclusive windows of `days` length."""
    cur = start
    while cur <= end:
        c_end = min(cur + timedelta(days=days - 1), end)
        yield cur, c_end
        cur = c_end + timedelta(days=1)


@retry(wait=wait_exponential(min=1, max=30), stop=stop_after_attempt(4))
def read(dtype: str, method: str, c0: date, c1: date,
         window_size: str | None = None, limit: int = 500) -> list[dict]:
    """Read all data points for [c0, c1], following pagination. Returns verbatim objects."""
    base = ["data", dtype, method, "--from", c0.isoformat(), "--to", c1.isoformat()]
    if method == "rollup" and window_size:
        base += ["--window-size", window_size]
    if method == "list":
        base += ["--limit", str(limit)]

    points: list[dict] = []
    token = None
    while True:
        resp = _run(base + (["--page-token", token] if token else []))
        # --raw wrapper key is dataPoints (list/daily) or rollupDataPoints (rollup)
        points.extend(resp.get("dataPoints") or resp.get("rollupDataPoints") or [])
        token = resp.get("nextPageToken")
        if not token:
            return points


def point_time(dtype: str, p: dict) -> str | None:
    """Best-available ISO timestamp for keying (does not modify the payload)."""
    if p.get("startTime"):                                   # rollup bucket
        return p["startTime"]
    cs = p.get("civilStartTime")                             # daily-rollup (raw)
    if cs and cs.get("date"):
        d = cs["date"]
        return f'{d["year"]:04d}-{d["month"]:02d}-{d["day"]:02d}T00:00:00Z'
    if p.get("date"):                                        # simplified daily
        return f'{p["date"]}T00:00:00Z'
    node = p.get(dtype.replace("-", "")) or next(
        (v for v in p.values() if isinstance(v, dict)), {})
    iv = node.get("interval") or {}
    return iv.get("startTime") or (node.get("sampleTime") or {}).get("physicalTime")
