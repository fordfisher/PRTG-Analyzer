from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, File, UploadFile, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from analyzer.analysis import apply_timeframe, run_analysis
from analyzer.status_data_parser import parse_status_data
from analyzer.version import ANALYZER_VERSION


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

APP_HOST = "127.0.0.1"
APP_PORT = 8077

app = FastAPI(title="PyPRTG_CLA", version=ANALYZER_VERSION)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(NoCacheStaticMiddleware)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

CACHE_DIR = Path(tempfile.gettempdir()) / "prtg_analyzer_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

JOBS: Dict[str, Dict[str, Any]] = {}
RESULT_MEMO: Dict[tuple[str, str, int], Dict[str, Any]] = {}
JOB_TTL_SECONDS = 60 * 60
RESULT_MEMO_LIMIT = 64


def _cache_path(file_hash: str) -> Path:
    return CACHE_DIR / f"{file_hash}.json"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _prune_jobs(now: Optional[float] = None) -> None:
    cutoff = (now or time.time()) - JOB_TTL_SECONDS
    for job_id, job in list(JOBS.items()):
        if job.get("status") in {"done", "error"} and float(job.get("created_at") or 0) < cutoff:
            JOBS.pop(job_id, None)


def _invalidate_result_memo(file_hash: str) -> None:
    for key in list(RESULT_MEMO):
        if key[0] == file_hash:
            RESULT_MEMO.pop(key, None)


def _load_cached_result(file_hash: str) -> Optional[Dict[str, Any]]:
    cache_path = _cache_path(file_hash)
    if not cache_path.exists():
        return None
    try:
        cached = _read_json(cache_path)
    except (json.JSONDecodeError, TypeError, OSError):
        cache_path.unlink(missing_ok=True)
        _invalidate_result_memo(file_hash)
        return None
    if cached.get("metadata", {}).get("analyzer_version") != ANALYZER_VERSION:
        cache_path.unlink(missing_ok=True)
        _invalidate_result_memo(file_hash)
        return None
    return cached


def _result_for_timeframe(file_hash: str, timeframe: Optional[str]) -> Dict[str, Any]:
    cache_path = _cache_path(file_hash)
    cached = _load_cached_result(file_hash)
    if cached is None or not cache_path.exists():
        raise HTTPException(status_code=404, detail="Result not found.")

    version_key = cache_path.stat().st_mtime_ns
    memo_key = (file_hash, timeframe or "all", version_key)
    memoized = RESULT_MEMO.get(memo_key)
    if memoized is not None:
        return memoized

    result = apply_timeframe(cached, timeframe)
    if len(RESULT_MEMO) >= RESULT_MEMO_LIMIT:
        RESULT_MEMO.clear()
    RESULT_MEMO[memo_key] = result
    return result


async def _iter_file_chunks(upload: UploadFile, hasher: "hashlib._Hash", tmp_path: Path) -> AsyncIterator[bytes]:
    with tmp_path.open("wb") as f:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            f.write(chunk)
            yield chunk


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Frontend not built yet.")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    core_log: UploadFile = File(...),
    status_data: Optional[UploadFile] = File(default=None),
) -> JSONResponse:
    """
    Accept a Core.log upload (and optionally a PRTG Status Data .htm),
    stream to temp files, compute hash, then analyze in the background.
    Client can poll progress via /api/progress/{job_id}.
    """
    hasher = hashlib.sha256()
    suffix = Path(core_log.filename or "core.log").suffix
    tmp_path = Path(tempfile.mkstemp(suffix=suffix)[1])

    bytes_processed = 0
    async for chunk in _iter_file_chunks(core_log, hasher, tmp_path):
        bytes_processed += len(chunk)

    status_snapshot: Optional[Dict[str, Any]] = None
    status_tmp_path: Optional[Path] = None
    if status_data is not None and status_data.filename:
        try:
            status_tmp_path = Path(tempfile.mkstemp(suffix=".htm")[1])
            with status_tmp_path.open("wb") as f:
                while True:
                    chunk = await status_data.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            status_snapshot = parse_status_data(status_tmp_path)
        except Exception:
            status_snapshot = None
        finally:
            if status_tmp_path:
                try:
                    os.remove(status_tmp_path)
                except OSError:
                    pass

    file_hash = hasher.hexdigest()
    cache_path = _cache_path(file_hash)
    _prune_jobs()

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "job_id": job_id,
        "hash": file_hash,
        "status": "queued",
        "created_at": time.time(),
        "error": None,
    }

    captured_snapshot = status_snapshot

    def _do_analyze() -> None:
        try:
            JOBS[job_id]["status"] = "analyzing"
            cached = _load_cached_result(file_hash)
            if cached is not None:
                if captured_snapshot is not None:
                    cached["status_snapshot"] = captured_snapshot
                    _write_json(cache_path, cached)
                    _invalidate_result_memo(file_hash)
                JOBS[job_id]["status"] = "done"
                return
            result: Dict[str, Any] = run_analysis(str(tmp_path), status_snapshot=captured_snapshot)
            _write_json(cache_path, result)
            _invalidate_result_memo(file_hash)
            JOBS[job_id]["status"] = "done"
        except Exception as e:  # pragma: no cover (surfaced to UI)
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    background_tasks.add_task(_do_analyze)
    return JSONResponse(content={"job_id": job_id, "hash": file_hash, "bytes": bytes_processed})


@app.get("/api/progress/{job_id}")
async def progress(job_id: str) -> StreamingResponse:
    _prune_jobs()
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def event_stream() -> AsyncIterator[bytes]:
        last_status: Optional[str] = None
        while True:
            job = JOBS.get(job_id)
            if not job:
                yield b"event: end\ndata: {}\n\n"
                return
            status = job.get("status")
            if status != last_status:
                payload = json.dumps({"job_id": job_id, "hash": job.get("hash"), "status": status, "error": job.get("error")})
                yield f"data: {payload}\n\n".encode("utf-8")
                last_status = status
            if status in ("done", "error"):
                yield b"event: end\ndata: {}\n\n"
                return
            await _sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


@app.get("/api/result/{file_hash}")
async def get_result(file_hash: str, timeframe: Optional[str] = Query(None)) -> JSONResponse:
    return JSONResponse(content=_result_for_timeframe(file_hash, timeframe))


@app.get("/api/export/json/{file_hash}")
async def export_json(file_hash: str, timeframe: Optional[str] = Query(None)) -> JSONResponse:
    return await get_result(file_hash, timeframe)


@app.get("/api/export/html/{file_hash}", response_class=HTMLResponse)
async def export_html(file_hash: str, timeframe: Optional[str] = Query(None)) -> HTMLResponse:
    from analyzer.report_generator import build_enterprise_html_report

    data = _result_for_timeframe(file_hash, timeframe)
    html = build_enterprise_html_report(data, errors_time_frame=timeframe)
    return HTMLResponse(html)
