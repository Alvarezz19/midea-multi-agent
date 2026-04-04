from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import config

DEFAULT_FLOW_DIR = Path("AHU\u7a0b\u5e8f")
DEFAULT_PATTERN_LIBRARY_DIR = Path(config.AHU_PATTERN_LIBRARY_DIR)
DEFAULT_SYSTEM_TYPE = "AHU"


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = text.strip()
    text = re.sub(r"[\uff08(][^\uff09)]*[\uff09)]", "", text)
    text = re.sub(r"[\s\u3000]+", " ", text)
    return text.strip(" _-/")


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _page_key_from_label(label: Any) -> str:
    normalized = _normalize_text(label)
    lowered = normalized.lower()

    if not normalized:
        return "page"
    if "io" in lowered or "\u901a\u8baf" in normalized or "\u901a\u4fe1" in normalized:
        return "io_comm"
    if "\u5b9a\u65f6" in normalized or "schedule" in lowered:
        return "timing"
    if "\u63a7\u5236" in normalized:
        return "control"
    if "\u6545\u969c" in normalized:
        if "\u76f4\u81a8" in normalized or "dx" in lowered:
            return "dx_fault"
        return "fault"
    if "\u72b6\u6001" in normalized:
        if "\u76f4\u81a8" in normalized or "dx" in lowered:
            return "dx_status"
        if "\u6392\u98ce" in normalized:
            return "exhaust_status"
        return "status"
    if "\u6392\u98ce\u673a" in normalized:
        return "exhaust_fan"
    if "\u6392\u98ce" in normalized:
        return "exhaust"
    if "\u65b0\u98ce" in normalized:
        return "fresh_air"
    if "\u9001\u98ce\u673a" in normalized or ("\u9001\u98ce" in normalized and "\u673a" in normalized):
        return "supply_fan"
    if "\u51b7\u6c34\u9600" in normalized or "\u51b7\u6c34" in normalized:
        return "chw_valve"
    if "\u7535\u52a0\u70ed" in normalized:
        return "heater"

    slug = _slugify(normalized)
    return slug or "page"


_PAGE_KIND_HINTS = {
    "io_comm": "io",
    "control": "control",
    "timing": "timing",
    "status": "status",
    "dx_status": "status",
    "dx_fault": "fault",
    "fault": "fault",
    "exhaust": "exhaust",
    "exhaust_fan": "fan",
    "exhaust_status": "status",
    "fresh_air": "air",
    "supply_fan": "fan",
    "chw_valve": "valve",
    "heater": "heater",
}


def _page_kind_from_key(page_key: str) -> str:
    if page_key in _PAGE_KIND_HINTS:
        return _PAGE_KIND_HINTS[page_key]
    if page_key.endswith("_status"):
        return "status"
    if page_key.endswith("_fault"):
        return "fault"
    return page_key.split("_")[-1] if "_" in page_key else "page"


def _extract_flow_objects(raw_payload: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_payload, list):
        return [copy.deepcopy(obj) for obj in raw_payload if isinstance(obj, dict)]

    if isinstance(raw_payload, dict):
        nodes = raw_payload.get("nodes")
        if isinstance(nodes, list):
            return [copy.deepcopy(obj) for obj in nodes if isinstance(obj, dict)]

        raw_json = raw_payload.get("rawJson")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                return _extract_flow_objects(json.loads(raw_json))
            except json.JSONDecodeError:
                return []
        if isinstance(raw_json, (list, dict)):
            return _extract_flow_objects(raw_json)

    return []


def _load_flow_document(path: Path) -> Dict[str, Any]:
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    objects = _extract_flow_objects(raw_payload)
    return {
        "source_path": path,
        "source_name": path.stem,
        "raw_payload": raw_payload,
        "objects": objects,
    }


def load_ahu_flow_documents(flows_dir: Path | str = DEFAULT_FLOW_DIR) -> List[Dict[str, Any]]:
    base_dir = Path(flows_dir)
    flow_files = sorted(base_dir.glob("flows_*.json"))
    return [_load_flow_document(path) for path in flow_files]


def _infer_template_role(template_name: str) -> str:
    name = _normalize_text(template_name)
    if "\u9001\u98ce\u673a" in name and "\u9891\u7387" in name:
        return "supply_fan_frequency_control"
    if "\u9001\u98ce\u673a" in name:
        return "supply_fan_control"
    if "\u65b0\u98ce" in name and "\u56de\u98ce" in name:
        return "air_damper_co2_control"
    if "\u51b7\u6c34\u9600" in name:
        return "chw_valve_control"
    if "\u7535\u52a0\u70ed" in name:
        return "heater_control"
    if "\u76f4\u81a8" in name:
        return "dx_control"
    return "subflow_control"


def _build_ports_definition(port_items: Iterable[Dict[str, Any]], direction: str) -> List[Dict[str, Any]]:
    ports: List[Dict[str, Any]] = []
    for index, port in enumerate(port_items):
        label = _normalize_text(port.get("name") or port.get("label") or f"{direction}_{index}")
        ports.append(
            {
                "index": index,
                "label": label,
                "name": label,
                "type": "any",
                "description": "",
                "condition": "always",
            }
        )
    return ports


def _build_subflow_signature(subflow_obj: Dict[str, Any]) -> Dict[str, Any]:
    input_ports = [port for port in subflow_obj.get("in", []) if isinstance(port, dict)]
    output_ports = [port for port in subflow_obj.get("out", []) if isinstance(port, dict)]
    return {
        "name": _normalize_text(subflow_obj.get("name", "")),
        "input_count": len(input_ports),
        "output_count": len(output_ports),
        "input_names": [_normalize_text(port.get("name", "")) for port in input_ports],
        "output_names": [_normalize_text(port.get("name", "")) for port in output_ports],
    }


def _build_subflow_template_asset(
    subflow_obj: Dict[str, Any],
    internal_objects: List[Dict[str, Any]],
    source_path: Path,
    system_type: str,
) -> Dict[str, Any]:
    raw_definition = copy.deepcopy(subflow_obj)
    signature_payload = _build_subflow_signature(subflow_obj)
    signature_payload["system_type"] = system_type
    signature_hash = hashlib.sha1(
        json.dumps(signature_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    input_count = signature_payload["input_count"]
    output_count = signature_payload["output_count"]
    template_id = f"{_slugify(system_type) or 'ahu'}_subflow__{input_count}in{output_count}out__{signature_hash[:10]}__v1"
    template_name = _normalize_text(subflow_obj.get("name", template_id)) or template_id
    template_role = _infer_template_role(template_name)

    raw_definition["id"] = template_id
    raw_definition["type"] = "subflow"
    raw_definition["name"] = template_name
    raw_definition["in"] = [copy.deepcopy(port) for port in subflow_obj.get("in", []) if isinstance(port, dict)]
    raw_definition["out"] = [copy.deepcopy(port) for port in subflow_obj.get("out", []) if isinstance(port, dict)]
    raw_definition["inputs"] = input_count
    raw_definition["outputs"] = output_count

    dependency_module_types = sorted(
        {
            obj.get("type")
            for obj in internal_objects
            if isinstance(obj, dict)
            and isinstance(obj.get("type"), str)
            and obj.get("type", "").startswith("subflow:")
        }
    )

    description = _normalize_text(subflow_obj.get("info", ""))
    if not description:
        description = f"{template_name} \u5b50\u6d41\u7a0b\u6a21\u677f"

    template_json = raw_definition
    template_json["template_id"] = template_id
    template_json["definition_id"] = template_id

    return {
        "module_type": template_id,
        "asset_type": "subflow_template",
        "template_id": template_id,
        "definition_id": template_id,
        "template_name": template_name,
        "template_role": template_role,
        "system_type": system_type,
        "description": description,
        "keywords": [],
        "usage_guides": [],
        "category": f"{system_type}\u5b50\u6d41\u7a0b\u6a21\u677f/{template_role}",
        "ports_definition": {
            "inputs": _build_ports_definition(raw_definition.get("in", []), "input"),
            "outputs": _build_ports_definition(raw_definition.get("out", []), "output"),
        },
        "parameters_schema": {},
        "template_json": template_json,
        "internal_flow_objects": [copy.deepcopy(obj) for obj in internal_objects],
        "dependency_module_types": dependency_module_types,
        "compile_hints": {
            "supports_multi_instance": True,
            "input_count": input_count,
            "output_count": output_count,
        },
        "source_info": {
            "source_flows": [source_path.name],
            "source_flow_paths": [str(source_path)],
            "original_subflow_id": str(subflow_obj.get("id", "")),
            "signature_hash": signature_hash,
        },
    }


def _merge_subflow_assets(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    existing_source = existing.setdefault("source_info", {})
    incoming_source = incoming.get("source_info", {})

    existing_flows = list(existing_source.get("source_flows", []))
    for flow_name in incoming_source.get("source_flows", []):
        if flow_name not in existing_flows:
            existing_flows.append(flow_name)
    existing_source["source_flows"] = existing_flows

    existing_paths = list(existing_source.get("source_flow_paths", []))
    for flow_path in incoming_source.get("source_flow_paths", []):
        if flow_path not in existing_paths:
            existing_paths.append(flow_path)
    existing_source["source_flow_paths"] = existing_paths

    if not existing_source.get("original_subflow_id"):
        existing_source["original_subflow_id"] = incoming_source.get("original_subflow_id", "")
    if not existing_source.get("signature_hash"):
        existing_source["signature_hash"] = incoming_source.get("signature_hash", "")

    existing_dependencies = set(existing.get("dependency_module_types", []))
    existing_dependencies.update(incoming.get("dependency_module_types", []))
    existing["dependency_module_types"] = sorted(existing_dependencies)

    if len(incoming.get("internal_flow_objects", [])) > len(existing.get("internal_flow_objects", [])):
        existing["internal_flow_objects"] = copy.deepcopy(incoming.get("internal_flow_objects", []))
        existing["template_json"] = copy.deepcopy(incoming.get("template_json", {}))
        existing["ports_definition"] = copy.deepcopy(incoming.get("ports_definition", {}))
        existing["compile_hints"] = copy.deepcopy(incoming.get("compile_hints", {}))

    return existing


def collect_subflow_templates(
    flow_documents: List[Dict[str, Any]],
    system_type: str = DEFAULT_SYSTEM_TYPE,
) -> List[Dict[str, Any]]:
    templates: Dict[str, Dict[str, Any]] = {}
    for document in flow_documents:
        objects = document.get("objects", []) or []
        source_path = Path(document.get("source_path", ""))
        for subflow_obj in [obj for obj in objects if isinstance(obj, dict) and obj.get("type") == "subflow"]:
            original_id = str(subflow_obj.get("id", ""))
            internal_objects = [
                copy.deepcopy(obj)
                for obj in objects
                if isinstance(obj, dict) and obj.get("z") == original_id
            ]
            asset = _build_subflow_template_asset(subflow_obj, internal_objects, source_path, system_type)
            template_id = asset["template_id"]
            if template_id in templates:
                templates[template_id] = _merge_subflow_assets(templates[template_id], asset)
            else:
                templates[template_id] = asset

    return sorted(templates.values(), key=lambda item: item["template_id"])


def _canonical_page_label(label: Any) -> str:
    normalized = _normalize_text(label)
    return normalized or _page_key_from_label(label)


def collect_system_patterns(
    flow_documents: List[Dict[str, Any]],
    system_type: str = DEFAULT_SYSTEM_TYPE,
) -> List[Dict[str, Any]]:
    if not flow_documents:
        return []

    page_counts: Counter[str] = Counter()
    labels_by_key: Dict[str, Counter[str]] = defaultdict(Counter)
    kinds_by_key: Dict[str, Counter[str]] = defaultdict(Counter)
    source_cases: List[Dict[str, Any]] = []

    for document in flow_documents:
        objects = document.get("objects", []) or []
        source_path = Path(document.get("source_path", ""))
        flow_page_map: Dict[str, Dict[str, Any]] = {}

        for page in [obj for obj in objects if isinstance(obj, dict) and obj.get("type") == "tab"]:
            label = _canonical_page_label(page.get("label", ""))
            page_key = _page_key_from_label(label)
            kind = _page_kind_from_key(page_key)
            flow_page_map[page_key] = {
                "page_key": page_key,
                "label": label,
                "kind": kind,
            }

        for page_key, page_entry in flow_page_map.items():
            page_counts[page_key] += 1
            labels_by_key[page_key][page_entry["label"]] += 1
            kinds_by_key[page_key][page_entry["kind"]] += 1

        source_cases.append(
            {
                "source_flow": source_path.name,
                "source_flow_path": str(source_path),
                "page_keys": sorted(flow_page_map.keys()),
                "page_labels": [entry["label"] for entry in flow_page_map.values()],
            }
        )

    total_flows = len(flow_documents)
    required_pages: List[Dict[str, Any]] = []
    optional_pages: List[Dict[str, Any]] = []

    for page_key in sorted(page_counts.keys()):
        count = page_counts[page_key]
        coverage = count / total_flows if total_flows else 0.0
        page_entry = {
            "page_key": page_key,
            "label": labels_by_key[page_key].most_common(1)[0][0],
            "kind": kinds_by_key[page_key].most_common(1)[0][0],
            "coverage_ratio": round(coverage, 3),
            "coverage_count": count,
        }
        if coverage >= 1.0:
            required_pages.append(page_entry)
        else:
            optional_pages.append(page_entry)

    required_keys = "_".join(item["page_key"] for item in required_pages) or "core"
    optional_keys = "_".join(item["page_key"] for item in optional_pages) or "plus"
    pattern_id = f"{_slugify(system_type) or 'ahu'}__{required_keys}__{optional_keys}__v1"

    pattern = {
        "pattern_id": pattern_id,
        "pattern_name": f"{system_type} \u63a7\u5236\u9aa8\u67b6",
        "system_type": system_type,
        "description": f"Derived from {total_flows} source flows.",
        "feature_tags": [system_type.lower(), "phase2", "ahu"],
        "required_pages": required_pages,
        "optional_pages": optional_pages,
        "subsystem_slots": [],
        "naming_hints": {},
        "layout_hints": {},
        "style_guides": {},
        "source_cases": source_cases,
    }
    return [pattern]


def build_ahu_knowledge_assets(
    flows_dir: Path | str = DEFAULT_FLOW_DIR,
    output_dir: Path | str | None = DEFAULT_PATTERN_LIBRARY_DIR,
    system_type: str = DEFAULT_SYSTEM_TYPE,
) -> Dict[str, Any]:
    flow_documents = load_ahu_flow_documents(flows_dir)
    subflow_templates = collect_subflow_templates(flow_documents, system_type=system_type)
    system_patterns = collect_system_patterns(flow_documents, system_type=system_type)

    assets = {
        "system_type": system_type,
        "source_flow_count": len(flow_documents),
        "source_flow_files": [str(document["source_path"]) for document in flow_documents],
        "subflow_templates": subflow_templates,
        "system_patterns": system_patterns,
        "manifest": {
            "flows_dir": str(Path(flows_dir)),
            "pattern_library_dir": str(Path(output_dir)) if output_dir is not None else "",
            "subflow_template_count": len(subflow_templates),
            "system_pattern_count": len(system_patterns),
        },
    }

    if output_dir is not None:
        write_pattern_library(output_dir, assets)

    return assets


def write_pattern_library(output_dir: Path | str, assets: Dict[str, Any]) -> Dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    files = {
        "subflow_templates": output_path / "subflow_templates.json",
        "system_patterns": output_path / "system_patterns.json",
        "manifest": output_path / "manifest.json",
    }

    files["subflow_templates"].write_text(
        json.dumps(assets.get("subflow_templates", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    files["system_patterns"].write_text(
        json.dumps(assets.get("system_patterns", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    files["manifest"].write_text(
        json.dumps(assets.get("manifest", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {name: str(path) for name, path in files.items()}


def load_structured_payload(metadata: Any) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    payload_json = metadata.get("payload_json")
    if isinstance(payload_json, dict):
        return copy.deepcopy(payload_json)
    if isinstance(payload_json, str) and payload_json.strip():
        try:
            return json.loads(payload_json)
        except json.JSONDecodeError:
            return {}

    json_schema = metadata.get("json_schema")
    if isinstance(json_schema, dict):
        return copy.deepcopy(json_schema)
    if isinstance(json_schema, str) and json_schema.strip():
        try:
            return json.loads(json_schema)
        except json.JSONDecodeError:
            return {}

    return {}


def _build_asset_document(asset: Dict[str, Any]) -> str:
    if asset.get("asset_type") == "subflow_template":
        return "\n".join(
            [
                asset.get("template_name", ""),
                asset.get("description", ""),
                asset.get("template_id", ""),
                asset.get("category", ""),
            ]
        ).strip()

    if asset.get("pattern_id"):
        required = ", ".join(page.get("page_key", "") for page in asset.get("required_pages", []))
        optional = ", ".join(page.get("page_key", "") for page in asset.get("optional_pages", []))
        return "\n".join(
            [
                asset.get("pattern_name", ""),
                asset.get("description", ""),
                f"required: {required}",
                f"optional: {optional}",
            ]
        ).strip()

    return json.dumps(asset, ensure_ascii=False)


def write_assets_to_chroma(
    assets: Dict[str, Any],
    persist_dir: Path | str | None = None,
    collection_names: Optional[Dict[str, str]] = None,
) -> Dict[str, int]:
    try:
        import chromadb  # type: ignore
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"chromadb is required to write indexes: {exc}") from exc

    from utils.model_manager import EmbeddingManager

    client = chromadb.PersistentClient(path=str(persist_dir or config.CHROMA_PERSIST_DIR))
    try:
        embedding_function = EmbeddingManager.get_embedding()
    except Exception:
        embedding_function = DefaultEmbeddingFunction()

    collection_names = collection_names or {
        "subflow_templates": config.CHROMA_COLLECTION_SUBFLOW_TEMPLATES,
        "system_patterns": config.CHROMA_COLLECTION_SYSTEM_PATTERNS,
    }

    counts = {"subflow_templates": 0, "system_patterns": 0}
    for asset_key, collection_name in collection_names.items():
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function,
            metadata={"description": f"Phase 2 {asset_key}"},
        )
        items = assets.get(asset_key, []) or []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []
        for item in items:
            item_id = item.get("template_id") or item.get("pattern_id")
            if not item_id:
                continue
            payload_json = json.dumps(item, ensure_ascii=False)
            documents.append(_build_asset_document(item))
            metadata = {
                "asset_type": item.get("asset_type", asset_key.rstrip("s")),
                "module_type": item_id,
                "payload_json": payload_json,
                "json_schema": payload_json,
            }
            metadata.update({key: value for key, value in item.items() if isinstance(value, (str, int, float, bool))})
            metadatas.append(metadata)
            ids.append(item_id)

        if documents:
            collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
            counts[asset_key] = len(documents)

    return counts


if __name__ == "__main__":
    assets = build_ahu_knowledge_assets()
    print(json.dumps(assets.get("manifest", {}), ensure_ascii=False, indent=2))
