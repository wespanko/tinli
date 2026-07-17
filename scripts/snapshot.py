"""Record cross-venue snapshots to parquet history (M6).

    python scripts/snapshot.py              one snapshot, written immediately
    python scripts/snapshot.py --loop 30    every 30s until Ctrl+C

Respects TINLI_DEMO (fixture source — useful only for testing the pipe;
fixture prices never change) and TINLI_HISTORY_DIR (default data/history).
In loop mode ticks are buffered and flushed every FLUSH_TICKS (and on exit),
so a recording day stays at hundreds of parquet files, not thousands.
"""

import argparse
import time
from datetime import UTC, datetime

from tinli_api.datasource import get_source
from tinli_api.history import history_dir, rows_from_items, write_rows
from tinli_api.screener import compute_all

FLUSH_TICKS = 10


def tick(source) -> list[dict]:
    ts = datetime.now(UTC)
    items = compute_all(source)
    rows = rows_from_items(items, ts)
    print(f"{ts:%H:%M:%S} captured {len(rows)} pairs", flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loop", type=int, metavar="SECONDS", help="record continuously")
    args = ap.parse_args()

    source = get_source()
    print(f"recording to {history_dir()}", flush=True)

    if not args.loop:
        path = write_rows(tick(source))
        print(f"wrote {path}", flush=True)
        return

    buffer: list[dict] = []
    ticks = 0
    try:
        while True:
            # a venue outage or disk hiccup must never kill the recorder —
            # log the miss, keep the loop alive, try again next interval
            try:
                buffer.extend(tick(source))
                ticks += 1
                if ticks % FLUSH_TICKS == 0:
                    path = write_rows(buffer)
                    print(f"flushed {len(buffer)} rows -> {path}", flush=True)
                    buffer = []
            except Exception as exc:
                print(f"tick/flush failed ({exc!r}) — retrying next interval", flush=True)
            time.sleep(args.loop)
    except KeyboardInterrupt:
        pass
    finally:
        if buffer:
            try:
                path = write_rows(buffer)
                print(f"final flush {len(buffer)} rows -> {path}", flush=True)
            except Exception as exc:
                print(f"final flush failed ({exc!r}) — {len(buffer)} rows lost", flush=True)


if __name__ == "__main__":
    main()
