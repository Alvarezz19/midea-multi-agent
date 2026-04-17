from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import re


TRACE_INDEX_DIRNAME = "_trace_index"


def generate_attempt_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _safe_thread_stem(thread_id: str) -> str:
    normalized = str(thread_id).strip()
    if not normalized:
        raise ValueError("thread_id 不能为空。")
    safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._-") or "thread"
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{safe_prefix[:48]}-{digest}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def register_trace_attempt(
    *,
    trace_output_root: str | Path,
    thread_id: str,
    attempt_id: str,
    trace_files: dict[str, str],
) -> dict[str, str]:
    root = Path(trace_output_root)
    safe_stem = _safe_thread_stem(thread_id)
    index_root = root / TRACE_INDEX_DIRNAME
    thread_index_path = index_root / "threads" / f"{safe_stem}.json"
    attempt_index_path = index_root / "attempts" / f"{safe_stem}__{attempt_id}.json"

    now = datetime.now().isoformat(timespec="seconds")
    attempt_record = {
        "thread_id": thread_id,
        "attempt_id": attempt_id,
        "created_at": now,
        "trace_dir": trace_files.get("trace_dir", ""),
        "summary_json": trace_files.get("summary_json", ""),
        "summary_md": trace_files.get("summary_md", ""),
        "final_state_json": trace_files.get("final_state_json", ""),
    }

    thread_payload = {
        "thread_id": thread_id,
        "updated_at": now,
        "attempts": [],
    }
    if thread_index_path.exists():
        thread_payload = json.loads(thread_index_path.read_text(encoding="utf-8"))
        thread_payload.setdefault("thread_id", thread_id)
        thread_payload.setdefault("attempts", [])
        thread_payload["updated_at"] = now

    attempts = []
    replaced = False
    for item in thread_payload.get("attempts", []):
        if str((item or {}).get("attempt_id", "")).strip() == attempt_id:
            attempts.append(attempt_record)
            replaced = True
        else:
            attempts.append(item)
    if not replaced:
        attempts.append(attempt_record)
    thread_payload["attempts"] = attempts

    _write_json(thread_index_path, thread_payload)
    _write_json(attempt_index_path, attempt_record)

    return {
        "thread_index_json": str(thread_index_path.resolve()),
        "attempt_index_json": str(attempt_index_path.resolve()),
    }
