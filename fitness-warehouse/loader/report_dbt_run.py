"""Parse a dbt run_results.json and report the outcome to BigQuery (raw._pipeline_runs).
Colocated in loader/ so it can reuse to_bigquery.py directly.

Deliberately never lets its own errors propagate -- a reporting failure should never
break the CI job. dbt itself is still what determines whether the job succeeds or
fails; this script only observes and records that outcome after the fact.

Usage:  python report_dbt_run.py --workflow dbt_run --results path/to/run_results.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _run_url():
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def _parse_timestamps(metadata, elapsed):
    """dbt's run_results.json only gives a 'generated_at' (~finish time) plus total
    elapsed_time -- approximate a start time by subtracting the two."""
    generated_at = metadata.get("generated_at")
    if not generated_at:
        now = datetime.now(timezone.utc).isoformat()
        return now, now
    started_at = generated_at
    if elapsed is not None:
        try:
            finish_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            started_at = (finish_dt - timedelta(seconds=elapsed)).isoformat()
        except ValueError:
            pass
    return started_at, generated_at


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True, help="e.g. dbt_run or dbt_test")
    parser.add_argument("--results", required=True, help="path to dbt's run_results.json")
    args = parser.parse_args()

    if not os.path.exists(args.results):
        print(f"report_dbt_run: {args.results} not found, nothing to report")
        return

    with open(args.results) as f:
        results = json.load(f)

    node_results = results.get("results", [])
    failed = [
        {"node": r["unique_id"], "status": r["status"], "message": (r.get("message") or "")[:300]}
        for r in node_results if r["status"] not in ("pass", "success")
    ]
    status = "failure" if failed else "success"

    metadata = results.get("metadata", {})
    elapsed = results.get("elapsed_time")
    started_at, finished_at = _parse_timestamps(metadata, elapsed)

    record = {
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "workflow": args.workflow,
        "trigger": os.environ.get("GITHUB_EVENT_NAME", "manual"),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": elapsed,
        "status": status,
        "error_source": failed[0]["node"] if failed else None,
        "error_message": "; ".join(f'{f["node"]}: {f["message"]}' for f in failed) or None,
        "run_url": _run_url(),
        "details": {
            "total_nodes": len(node_results),
            "passed": len(node_results) - len(failed),
            "failed": len(failed),
            "failed_nodes": [f["node"] for f in failed],
        },
    }

    try:
        from google.cloud import bigquery
        from to_bigquery import PROJECT, write_run_log
        client = bigquery.Client(project=PROJECT)
        write_run_log(client, record)
    except Exception as e:
        print(f"report_dbt_run: failed to write BigQuery log: {e}")

    print(f"report_dbt_run: {args.workflow} -> {status} ({len(failed)} failed of {len(node_results)})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"report_dbt_run: unexpected error, not failing the job: {e}")
