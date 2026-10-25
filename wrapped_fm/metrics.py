"""Counters shared across nodes.

Each node only ever adds to its own rows (node, metric, day). Nodes pull each
other's rows and keep the max per row, so totals converge without double
counting and any node can go down without losing what it already reported.
The old single-file counter and template-uses.json are imported once as the
"legacy" node.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from . import cluster
from .config import (
    CLUSTER_SYNC_INTERVAL,
    COUNTER_DB,
    NODE_ID,
    TEMPLATE_LIBRARY_DIR,
    WRAPPED_COUNT_FILE,
)

logger = logging.getLogger("wrapped_fm")

LEGACY_NODE = "legacy"
LEGACY_USES_FILE = Path(TEMPLATE_LIBRARY_DIR).parent / "template-uses.json"
WRAPPED = "wrapped"
TEMPLATE_PREFIX = "template:"
SERVICE_PREFIX = "wrapped:"
SERVICES = ("listenbrainz", "lastfm", "librefm", "navidrome")

_METRIC_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,79}$")
_DAY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})?$")
_MAX_VALUE = 10 ** 12

Row = Tuple[str, str, str, int]

_init_lock = threading.Lock()
_initialised: set = set()


def _connect() -> sqlite3.Connection:
    path = Path(COUNTER_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 10000")
    key = str(path.resolve())
    if key not in _initialised:
        with _init_lock:
            if key not in _initialised:
                _initialise(conn)
                _initialised.add(key)
    return conn


def _initialise(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS counts ("
        " node TEXT NOT NULL, metric TEXT NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL,"
        " PRIMARY KEY (node, metric, day))"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("BEGIN IMMEDIATE")
    try:
        done = conn.execute("SELECT 1 FROM meta WHERE key = 'legacy_imported'").fetchone()
        if not done:
            rows = _legacy_rows()
            conn.executemany(
                "INSERT INTO counts (node, metric, day, n) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (node, metric, day) DO UPDATE SET n = max(n, excluded.n)",
                rows,
            )
            conn.execute("INSERT INTO meta (key, value) VALUES ('legacy_imported', ?)", (str(int(time.time())),))
            if rows:
                logger.info("Imported %d legacy counter rows", len(rows))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _legacy_rows() -> List[Row]:
    rows: List[Row] = []
    try:
        total = int(Path(WRAPPED_COUNT_FILE).read_text().strip() or "0")
    except (OSError, ValueError):
        total = 0
    if total > 0:
        rows.append((LEGACY_NODE, WRAPPED, "", total))
    try:
        uses = json.loads(Path(LEGACY_USES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        uses = {}
    if isinstance(uses, dict):
        for slug, value in uses.items():
            metric = f"{TEMPLATE_PREFIX}{slug}"
            if isinstance(value, (int, float)) and value > 0 and _METRIC_RE.match(metric):
                rows.append((LEGACY_NODE, metric, "", int(value)))
    return rows


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def increment(metric: str, delta: int = 1) -> int:
    if not _METRIC_RE.match(metric):
        raise ValueError(f"invalid metric name: {metric!r}")
    step = max(int(delta), 0)
    with closing(_connect()) as conn:
        if step:
            conn.execute(
                "INSERT INTO counts (node, metric, day, n) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (node, metric, day) DO UPDATE SET n = n + excluded.n",
                (NODE_ID, metric, _today(), step),
            )
        return _total(conn, metric)


def _total(conn: sqlite3.Connection, metric: str) -> int:
    row = conn.execute("SELECT COALESCE(SUM(n), 0) FROM counts WHERE metric = ?", (metric,)).fetchone()
    return int(row[0])


def read_total(metric: str) -> int:
    maybe_sync()
    with closing(_connect()) as conn:
        return _total(conn, metric)


def read_totals(prefix: str) -> Dict[str, int]:
    maybe_sync()
    pattern = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT metric, SUM(n) FROM counts WHERE metric LIKE ? ESCAPE '\\' GROUP BY metric",
            (pattern,),
        ).fetchall()
    return {metric[len(prefix):]: int(total) for metric, total in rows}


def read_wrapped_count() -> int:
    return read_total(WRAPPED)


def increment_wrapped_count(delta: int = 1, service: Optional[str] = None) -> int:
    total = increment(WRAPPED, delta)
    if service in SERVICES:
        increment(f"{SERVICE_PREFIX}{service}", delta)
    return total


def read_stats(days: int = 30) -> Dict[str, object]:
    maybe_sync()
    with closing(_connect()) as conn:
        total = _total(conn, WRAPPED)
        daily = conn.execute(
            "SELECT day, SUM(n) FROM counts WHERE metric = ? AND day != ''"
            " GROUP BY day ORDER BY day DESC LIMIT ?",
            (WRAPPED, max(1, min(days, 366))),
        ).fetchall()
    services = read_totals(SERVICE_PREFIX)
    return {
        "total": total,
        "services": {name: services.get(name, 0) for name in SERVICES},
        "days": [{"day": day, "count": int(n)} for day, n in reversed(daily)],
    }


def export_rows() -> List[Row]:
    with closing(_connect()) as conn:
        return [tuple(row) for row in conn.execute("SELECT node, metric, day, n FROM counts")]


def _clean_rows(rows: Iterable) -> List[Row]:
    clean: List[Row] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            continue
        node, metric, day, n = row
        if not (isinstance(node, str) and 0 < len(node) <= 64):
            continue
        if not (isinstance(metric, str) and _METRIC_RE.match(metric)):
            continue
        if not (isinstance(day, str) and _DAY_RE.match(day)):
            continue
        if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < _MAX_VALUE:
            continue
        clean.append((node, metric, day, n))
    return clean


def merge_rows(rows: Iterable) -> int:
    clean = _clean_rows(rows)
    if not clean:
        return 0
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.executemany(
                "INSERT INTO counts (node, metric, day, n) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (node, metric, day) DO UPDATE SET n = max(n, excluded.n)",
                clean,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return len(clean)


def sync_peers() -> Dict[str, bool]:
    results: Dict[str, bool] = {}
    for peer in cluster.peers():
        try:
            response = cluster.peer_get(peer, "/internal/counters")
            response.raise_for_status()
            payload = response.json()
            merge_rows(payload.get("rows", []) if isinstance(payload, dict) else [])
            results[peer] = True
        except (requests.RequestException, ValueError, sqlite3.Error) as error:
            logger.warning("Counter sync with %s failed: %s", peer, error)
            results[peer] = False
    return results


def maybe_sync() -> None:
    if cluster.peers():
        cluster.every("counters", CLUSTER_SYNC_INTERVAL, sync_peers)
