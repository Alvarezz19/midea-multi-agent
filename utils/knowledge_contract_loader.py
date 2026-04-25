"""知识资产合同加载器。

本模块只从事实源读取结构化合同：原子模块来自 ``schemas/*.json``，
AHU 子流程模板来自 ``AHU程序/pattern_library/subflow_templates.json``。
调用方拿到的是深拷贝，避免运行时修改污染缓存。
"""
from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMAS_DIR = PROJECT_ROOT / "schemas"
DEFAULT_SUBFLOW_TEMPLATES_FILE = PROJECT_ROOT / "AHU程序" / "pattern_library" / "subflow_templates.json"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locator(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _iter_contract_dicts(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _normalize_module_contract(contract: dict[str, Any], source_path: Path, source_hash: str) -> dict[str, Any]:
    module_type = str(contract.get("module_type", "")).strip()
    if not module_type:
        return {}

    normalized = copy.deepcopy(contract)
    normalized.setdefault("name", "")
    normalized.setdefault("description", "")
    normalized.setdefault("category", "")
    normalized.setdefault("parameters_schema", {})
    normalized.setdefault("ports_definition", {})
    normalized.setdefault("template_json", {})
    normalized.setdefault("keywords", [])
    normalized.setdefault("usage_guides", [])
    normalized["asset_id"] = f"module::{module_type}"
    normalized["asset_type"] = "atomic_module"
    normalized["asset_level"] = "L2"
    normalized["source_path"] = _locator(source_path)
    normalized["source_hash"] = source_hash
    return normalized


@lru_cache(maxsize=8)
def _load_module_contract_index(schemas_dir: str) -> dict[str, dict[str, Any]]:
    root = Path(schemas_dir)
    contracts: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return contracts

    for path in sorted(root.rglob("*.json")):
        source_hash = _source_hash(path)
        try:
            payload = _read_json(path)
        except json.JSONDecodeError:
            continue
        for item in _iter_contract_dicts(payload):
            normalized = _normalize_module_contract(item, path, source_hash)
            module_type = normalized.get("module_type", "")
            if module_type:
                contracts[module_type] = normalized
    return contracts


def load_all_module_contracts(schemas_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """加载全部原子模块合同，key 为 ``module_type``。"""
    root = Path(schemas_dir) if schemas_dir is not None else DEFAULT_SCHEMAS_DIR
    return copy.deepcopy(_load_module_contract_index(str(root.resolve())))


def load_module_contract(module_type: str, schemas_dir: str | Path | None = None) -> dict[str, Any]:
    """按 ``module_type`` 加载单个原子模块 L2 合同。"""
    normalized_type = str(module_type or "").strip()
    if not normalized_type:
        return {}

    contracts = load_all_module_contracts(schemas_dir)
    if normalized_type in contracts:
        return contracts[normalized_type]

    lowered = normalized_type.lower()
    for key, value in contracts.items():
        if key.lower() == lowered:
            return copy.deepcopy(value)
    return {}


def _normalize_subflow_template(template: dict[str, Any], source_path: Path, source_hash: str) -> dict[str, Any]:
    raw_template = template.get("template_json", {})
    raw_definition_id = ""
    if isinstance(raw_template, dict):
        raw_definition_id = str(raw_template.get("id", "")).strip()

    template_id = str(template.get("template_id") or template.get("definition_id") or raw_definition_id).strip()
    if not template_id:
        return {}

    normalized = copy.deepcopy(template)
    normalized["asset_id"] = f"subflow_template::{template_id}"
    normalized["asset_type"] = "subflow_template"
    normalized["asset_level"] = "L2/L3"
    normalized["template_id"] = template_id
    normalized.setdefault("definition_id", raw_definition_id or template_id)
    normalized.setdefault("module_type", template_id)
    normalized.setdefault("template_name", normalized.get("name", template_id))
    normalized.setdefault("parameters_schema", {})
    normalized.setdefault("ports_definition", {})
    normalized.setdefault("internal_flow_objects", [])
    normalized["source_path"] = _locator(source_path)
    normalized["source_hash"] = source_hash
    return normalized


@lru_cache(maxsize=8)
def _load_subflow_template_index(template_file: str) -> dict[str, dict[str, Any]]:
    path = Path(template_file)
    if not path.exists():
        return {}

    payload = _read_json(path)
    if not isinstance(payload, list):
        return {}

    source_hash = _source_hash(path)
    index: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_subflow_template(item, path, source_hash)
        if not normalized:
            continue
        aliases = {
            str(normalized.get("template_id", "")).strip(),
            str(normalized.get("definition_id", "")).strip(),
            str(normalized.get("module_type", "")).strip(),
        }
        raw_template = normalized.get("template_json", {})
        if isinstance(raw_template, dict):
            aliases.add(str(raw_template.get("id", "")).strip())
        for alias in aliases:
            if alias and alias not in index:
                index[alias] = normalized
    return index


def load_subflow_template_contract(
    template_id: str,
    template_file: str | Path | None = None,
) -> dict[str, Any]:
    """按 ``template_id`` 或 ``definition_id`` 加载子流程模板合同。"""
    normalized_id = str(template_id or "").strip()
    if not normalized_id:
        return {}
    path = Path(template_file) if template_file is not None else DEFAULT_SUBFLOW_TEMPLATES_FILE
    return copy.deepcopy(_load_subflow_template_index(str(path.resolve())).get(normalized_id, {}))


def find_subflow_template_contract(
    *,
    template_role: str = "",
    name_contains: str = "",
    template_file: str | Path | None = None,
) -> dict[str, Any]:
    """按角色或名称查找子流程模板合同，返回第一条稳定匹配。"""
    role = str(template_role or "").strip()
    name_part = str(name_contains or "").strip()
    path = Path(template_file) if template_file is not None else DEFAULT_SUBFLOW_TEMPLATES_FILE
    seen_ids: set[str] = set()
    for item in _load_subflow_template_index(str(path.resolve())).values():
        template_id = str(item.get("template_id", "")).strip()
        if template_id in seen_ids:
            continue
        seen_ids.add(template_id)
        role_matches = not role or str(item.get("template_role", "")).strip() == role
        name = str(item.get("template_name") or item.get("name") or "").strip()
        name_matches = not name_part or name_part in name
        if role_matches and name_matches:
            return copy.deepcopy(item)
    return {}


__all__ = [
    "DEFAULT_SCHEMAS_DIR",
    "DEFAULT_SUBFLOW_TEMPLATES_FILE",
    "find_subflow_template_contract",
    "load_all_module_contracts",
    "load_module_contract",
    "load_subflow_template_contract",
]
