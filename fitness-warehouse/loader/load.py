"""Orchestrate extraction: per source, resume from disk, chunk, pull, write NDJSON.

Run from anywhere:  python loader/load.py
"""
import os
import sys
import yaml
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ghealth_client import read, chunks, point_time   # noqa: E402
from sink_files import write_chunk, last_chunk_end, first_chunk_start   # noqa: E402
import run_log   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
out = os.path.join(ROOT, cfg["output_dir"])
today = date.today()
logger = run_log.setup(os.path.join(ROOT, "logs"))


def main():
    run_start = datetime.now()
    cfg_start = date.fromisoformat(cfg["backfill_start_date"])
    total_chunks = 0
    total_points = 0

    for s in cfg["sources"]:
        dtype, method = s["type"], s["method"]
        window, cdays = s.get("window_size"), s.get("chunk_days", 90)

        first, last = first_chunk_start(out, dtype), last_chunk_end(out, dtype)

        # gaps to fill: further back than what's on disk, and/or further forward than what's on disk
        ranges = []
        if first is None:
            ranges.append((cfg_start, today))
        else:
            if cfg_start < first:
                ranges.append((cfg_start, first - timedelta(days=1)))
            if last < today:
                ranges.append((last + timedelta(days=1), today))

        if not ranges:
            logger.info(f"{dtype:14} up to date")
            continue

        logger.info(f"{dtype:14} ranges to fill: {ranges}")

        source_chunks = 0
        source_points = 0
        for range_start, range_end in ranges:
            for c0, c1 in chunks(range_start, range_end, cdays):
                pts = read(dtype, method, c0, c1, window_size=window)
                path, n = write_chunk(out, dtype, method, c0, c1, pts, point_time)
                logger.info(f"{dtype:14} {c0}..{c1}: {n:5} -> {os.path.relpath(path, ROOT)}")
                source_chunks += 1
                source_points += n

        logger.info(f"{dtype:14} done: {source_chunks} chunks, {source_points} points")
        total_chunks += source_chunks
        total_points += source_points

    run_end = datetime.now()
    logger.info(
        f"run summary: start={run_start.isoformat()} end={run_end.isoformat()} "
        f"duration={run_end - run_start} sources={len(cfg['sources'])} "
        f"total_chunks={total_chunks} total_points={total_points}"
    )


if __name__ == "__main__":
    main()
