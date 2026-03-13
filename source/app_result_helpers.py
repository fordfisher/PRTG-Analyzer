"""Result cache and timeframe logic for analysis API. Kept separate from route definitions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from analyzer.analysis import apply_timeframe


def cache_path(cache_dir: Path, file_hash: str) -> Path:
    return cache_dir / f"{file_hash}.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def prune_jobs(jobs: Dict[str, Dict[str, Any]], ttl_seconds: float, now: Optional[float] = None) -> None:
    cutoff = (now or time.time()) - ttl_seconds
    for job_id, job in list(jobs.items()):
        if job.get("status") in {"done", "error"} and float(job.get("created_at") or 0) < cutoff:
            jobs.pop(job_id, None)


def invalidate_result_memo(memo: Dict[tuple[str, str, int], Dict[str, Any]], file_hash: str) -> None:
    for key in list(memo):
        if key[0] == file_hash:
            memo.pop(key, None)


def load_cached_result(
    cache_dir: Path,
    file_hash: str,
    current_version: str,
    result_memo: Dict[tuple[str, str, int], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    path = cache_path(cache_dir, file_hash)
    if not path.exists():
        return None
    try:
        cached = read_json(path)
    except (json.JSONDecodeError, TypeError, OSError):
        path.unlink(missing_ok=True)
        invalidate_result_memo(result_memo, file_hash)
        return None
    if cached.get("metadata", {}).get("analyzer_version") != current_version:
        path.unlink(missing_ok=True)
        invalidate_result_memo(result_memo, file_hash)
        return None
    return cached


def result_for_timeframe(
    cache_dir: Path,
    file_hash: str,
    timeframe: Optional[str],
    result_memo: Dict[tuple[str, str, int], Dict[str, Any]],
    memo_limit: int,
    current_version: str,
    apply_fn: Callable[[Dict[str, Any], Optional[str]], Dict[str, Any]] = apply_timeframe,
) -> Optional[Dict[str, Any]]:
    path = cache_path(cache_dir, file_hash)
    cached = load_cached_result(cache_dir, file_hash, current_version, result_memo)
    if cached is None or not path.exists():
        return None

    version_key = path.stat().st_mtime_ns
    memo_key = (file_hash, timeframe or "all", version_key)
    if memo_key in result_memo:
        return result_memo[memo_key]

    result = apply_fn(cached, timeframe)
    if len(result_memo) >= memo_limit:
        result_memo.clear()
    result_memo[memo_key] = result
    return result
