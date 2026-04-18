from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import re


TRACE_INDEX_DIRNAME = "_trace_index"


def _safe_thread_stem(thread_id: str) -> str:
    normalized = str(thread_id).strip()
    if not normalized:
        raise ValueError("thread_id 不能为空。")
    safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._-") or "thread"
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{safe_prefix[:48]}-{digest}"


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _review_record_from_entry(
    entry: dict[str, Any],
    *,
    thread_id: str,
    attempt_id: str,
    trace_files: dict[str, str],
) -> dict[str, Any]:
    request = dict(entry.get("request", {}) or {})
    response = dict(entry.get("response", {}) or {})
    review_id = str(
        entry.get("review_id", "")
        or request.get("review_id", "")
        or response.get("review_id", "")
        or ""
    ).strip()
    stage = str(entry.get("stage", "") or request.get("stage", "") or "none").strip() or "none"
    status = str(entry.get("status", "") or "none").strip() or "none"
    created_at = (
        str(entry.get("created_at", "") or "").strip()
        or str(request.get("created_at", "") or "").strip()
        or datetime.now().isoformat(timespec="seconds")
    )
    updated_at = str(entry.get("updated_at", "") or "").strip() or created_at
    decision = str(response.get("decision", "") or "").strip()

    return {
        "thread_id": thread_id,
        "attempt_id": attempt_id,
        "review_id": review_id,
        "review_stage": stage,
        "review_status": status,
        "decision": decision,
        "resume_value": response,
        "request": request,
        "response": response,
        "created_at": created_at,
        "updated_at": updated_at,
        "trace_dir": trace_files.get("trace_dir", ""),
        "summary_json": trace_files.get("summary_json", ""),
        "summary_md": trace_files.get("summary_md", ""),
        "final_state_json": trace_files.get("final_state_json", ""),
    }


def save_review_artifacts(
    *,
    trace_output_root: str | Path,
    trace_dir: str | Path,
    thread_id: str | None,
    attempt_id: str,
    review_history: list[dict[str, Any]] | None,
    trace_files: dict[str, str],
) -> dict[str, Any]:
    records = [
        _review_record_from_entry(
            dict(entry or {}),
            thread_id=str(thread_id or "").strip(),
            attempt_id=attempt_id,
            trace_files=trace_files,
        )
        for entry in (review_history or [])
        if str((entry or {}).get("review_id", "") or "").strip()
    ]

    local_paths = {
        "review_records_json": "",
        "approval_record_json": "",
        "review_attempt_index_json": "",
        "review_thread_index_json": "",
        "review_record_jsons": [],
    }
    if not records:
        return local_paths

    trace_dir_path = Path(trace_dir)
    review_records_path = trace_dir_path / "review_records.json"
    approval_record_path = trace_dir_path / "approval_record.json"
    _write_json(review_records_path, records)
    _write_json(approval_record_path, records[-1])

    local_paths["review_records_json"] = str(review_records_path.resolve())
    local_paths["approval_record_json"] = str(approval_record_path.resolve())

    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return local_paths

    safe_stem = _safe_thread_stem(normalized_thread_id)
    root = Path(trace_output_root)
    index_root = root / TRACE_INDEX_DIRNAME
    review_root = index_root / "reviews"
    thread_index_path = index_root / "review_threads" / f"{safe_stem}.json"
    attempt_index_path = index_root / "review_attempts" / f"{safe_stem}__{attempt_id}.json"

    review_record_paths: list[str] = []
    review_refs: list[dict[str, Any]] = []
    for record in records:
        record_path = review_root / f"{safe_stem}__{attempt_id}__{record['review_id']}.json"
        _write_json(record_path, record)
        resolved = str(record_path.resolve())
        review_record_paths.append(resolved)
        review_refs.append(
            {
                "thread_id": normalized_thread_id,
                "attempt_id": attempt_id,
                "review_id": record["review_id"],
                "review_stage": record["review_stage"],
                "review_status": record["review_status"],
                "decision": record["decision"],
                "created_at": record["created_at"],
                "updated_at": record["updated_at"],
                "review_record_json": resolved,
            }
        )

    now = datetime.now().isoformat(timespec="seconds")
    attempt_payload = {
        "thread_id": normalized_thread_id,
        "attempt_id": attempt_id,
        "created_at": now,
        "review_count": len(review_refs),
        "reviews": review_refs,
        "approval_record_json": local_paths["approval_record_json"],
        "review_records_json": local_paths["review_records_json"],
    }
    _write_json(attempt_index_path, attempt_payload)

    thread_payload = {
        "thread_id": normalized_thread_id,
        "updated_at": now,
        "reviews": [],
    }
    if thread_index_path.exists():
        thread_payload = json.loads(thread_index_path.read_text(encoding="utf-8"))
        thread_payload.setdefault("thread_id", normalized_thread_id)
        thread_payload.setdefault("reviews", [])
        thread_payload["updated_at"] = now

    existing_reviews = []
    replaced_review_keys: set[tuple[str, str]] = set()
    incoming_keys = {
        (str(item.get("attempt_id", "")).strip(), str(item.get("review_id", "")).strip())
        for item in review_refs
    }
    for item in thread_payload.get("reviews", []):
        key = (str((item or {}).get("attempt_id", "")).strip(), str((item or {}).get("review_id", "")).strip())
        if key in incoming_keys:
            if key in replaced_review_keys:
                continue
            replacement = next(
                review for review in review_refs
                if (review["attempt_id"], review["review_id"]) == key
            )
            existing_reviews.append(replacement)
            replaced_review_keys.add(key)
        else:
            existing_reviews.append(item)
    for review in review_refs:
        key = (review["attempt_id"], review["review_id"])
        if key not in replaced_review_keys:
            existing_reviews.append(review)
    thread_payload["reviews"] = existing_reviews
    _write_json(thread_index_path, thread_payload)

    local_paths["review_attempt_index_json"] = str(attempt_index_path.resolve())
    local_paths["review_thread_index_json"] = str(thread_index_path.resolve())
    local_paths["review_record_jsons"] = review_record_paths
    return local_paths
