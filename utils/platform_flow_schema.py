"""平台 flow JSON 的最小结构化校验。

第一轮只覆盖最终 flow 文件的硬不变量，并按需消费
``schemas/*.json`` 中的原子模块合同。
"""
from __future__ import annotations

import re
from typing import Any

from utils.knowledge_contract_loader import load_all_module_contracts


PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")
QUOTE_REF_RE = re.compile(r"\[([^:\]]+):(\d+)\]")
DEFAULT_VALIDATED_MODULE_TYPES = {"swInput", "quote", "pid", "modbusOutput"}


def _issue(rule_id: str, target_id: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "severity": "error",
        "rule_id": rule_id,
        "target_id": str(target_id or ""),
        "message": message,
        "details": details or {},
    }


def _warning(rule_id: str, target_id: str, message: str) -> dict[str, Any]:
    return {
        "severity": "warning",
        "rule_id": rule_id,
        "target_id": str(target_id or ""),
        "message": message,
    }


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    return False


def _normalize_template(template_raw: Any) -> dict[str, Any]:
    if isinstance(template_raw, list):
        if template_raw and isinstance(template_raw[0], dict):
            return dict(template_raw[0])
        return {}
    if isinstance(template_raw, dict):
        return dict(template_raw)
    return {}


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _param_value(obj: dict[str, Any], field_name: str) -> tuple[Any, bool]:
    if field_name in obj:
        return obj.get(field_name), False
    if field_name in {"inputCount", "inputsCount"} and "inputs" in obj:
        return obj.get("inputs"), True
    if field_name in {"outputCount", "outputsCount"} and "outputs" in obj:
        return obj.get("outputs"), True
    return None, False


def _validate_parameter_contract(
    obj: dict[str, Any],
    contract: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    obj_id = str(obj.get("id") or obj.get("type") or "")
    parameters_schema = contract.get("parameters_schema", {})
    if not isinstance(parameters_schema, dict):
        return

    for field_name, schema in parameters_schema.items():
        if not isinstance(schema, dict):
            continue
        value, value_from_port_alias = _param_value(obj, field_name)
        if value is None:
            continue

        schema_type = str(schema.get("type", "")).strip().lower()
        numeric_value: float | None = None
        if schema_type in {"integer", "non_negative_integer", "unsigned integer"}:
            numeric_value = _coerce_number(value)
            if numeric_value is None:
                issues.append(_issue("flow.contract.parameter.type", obj_id, f"{field_name} 必须是整数。"))
                continue
            if int(numeric_value) != numeric_value:
                issues.append(_issue("flow.contract.parameter.type", obj_id, f"{field_name} 必须是整数。"))
                continue
        elif schema_type == "number":
            numeric_value = _coerce_number(value)
            if numeric_value is None:
                issues.append(_issue("flow.contract.parameter.type", obj_id, f"{field_name} 必须是数字。"))
                continue
        elif schema_type == "boolean":
            if not isinstance(value, bool):
                issues.append(_issue("flow.contract.parameter.type", obj_id, f"{field_name} 必须是布尔值。"))
                continue
        elif schema_type == "string":
            if not isinstance(value, str):
                issues.append(_issue("flow.contract.parameter.type", obj_id, f"{field_name} 必须是字符串。"))
                continue

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            values = value if isinstance(value, list) else [value]
            invalid_values = [item for item in values if item not in enum_values]
            if invalid_values:
                issues.append(_issue(
                    "flow.contract.parameter.enum",
                    obj_id,
                    f"{field_name} 存在非法枚举值: {invalid_values}",
                    {"field": field_name, "invalid_values": invalid_values},
                ))

        if numeric_value is not None:
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if isinstance(minimum, (int, float)) and numeric_value < minimum and not value_from_port_alias:
                issues.append(_issue("flow.contract.parameter.minimum", obj_id, f"{field_name} 小于最小值 {minimum}。"))
            if isinstance(maximum, (int, float)) and numeric_value > maximum:
                issues.append(_issue("flow.contract.parameter.maximum", obj_id, f"{field_name} 大于最大值 {maximum}。"))


def _validate_port_contract(
    obj: dict[str, Any],
    contract: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    obj_id = str(obj.get("id") or obj.get("type") or "")
    ports_definition = contract.get("ports_definition", {})
    if not isinstance(ports_definition, dict):
        return

    for field_name in ("inputs", "outputs"):
        if field_name not in obj:
            continue
        value = obj.get(field_name)
        if not _is_non_negative_int(value):
            issues.append(_issue("flow.contract.port_count.type", obj_id, f"{field_name} 必须是非负整数。"))
            continue

        declared_ports = ports_definition.get(field_name, [])
        if not isinstance(declared_ports, list) or not declared_ports:
            continue
        declared_indexes = [
            port.get("index")
            for port in declared_ports
            if isinstance(port, dict) and isinstance(port.get("index"), int)
        ]
        if declared_indexes and value > max(declared_indexes) + 1:
            issues.append(_issue(
                "flow.contract.port_count.range",
                obj_id,
                f"{field_name}={value} 超过合同端口数量 {max(declared_indexes) + 1}。",
            ))


def _validate_contracts(
    flow_objects: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    module_contracts: dict[str, dict[str, Any]] | None = None,
) -> None:
    contracts = module_contracts if module_contracts is not None else load_all_module_contracts()
    for obj in flow_objects:
        obj_type = str(obj.get("type", "")).strip()
        if not obj_type or obj_type in {"tab", "subflow"} or obj_type.startswith("subflow:"):
            continue
        if module_contracts is None and obj_type not in DEFAULT_VALIDATED_MODULE_TYPES:
            continue
        contract = contracts.get(obj_type)
        if not contract:
            continue

        template = _normalize_template(contract.get("template_json", {}))
        template_type = str(template.get("type", "")).strip()
        if template_type and template_type != obj_type:
            issues.append(_issue(
                "flow.contract.template_type.must_match",
                str(obj.get("id") or obj_type),
                f"模块合同 template_json.type={template_type} 与节点 type={obj_type} 不一致。",
            ))

        _validate_parameter_contract(obj, contract, issues)
        _validate_port_contract(obj, contract, issues)


def validate_flow_document(
    flow_objects: Any,
    *,
    module_contracts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """校验平台 flow 对象数组，返回结构化报告。"""
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    metrics = {
        "object_count": 0,
        "page_count": 0,
        "subflow_count": 0,
        "subflow_instance_count": 0,
        "body_node_count": 0,
    }

    if not isinstance(flow_objects, list):
        issues.append(_issue("flow.document.must_be_list", "flow_objects", "顶层 flow document 必须是列表。"))
        return {"status": "failed", "issues": issues, "warnings": warnings, "metrics": metrics}

    metrics["object_count"] = len(flow_objects)
    dict_objects: list[dict[str, Any]] = []
    id_counts: dict[str, int] = {}

    for index, obj in enumerate(flow_objects):
        if not isinstance(obj, dict):
            issues.append(_issue("flow.object.must_be_dict", f"flow_objects[{index}]", "flow 对象必须是字典。"))
            continue
        dict_objects.append(obj)
        obj_id = str(obj.get("id", "")).strip()
        if not obj_id:
            issues.append(_issue("flow.object.id.required", f"flow_objects[{index}]", "每个 flow 对象必须有非空 id。"))
        else:
            id_counts[obj_id] = id_counts.get(obj_id, 0) + 1
        if _contains_placeholder(obj):
            issues.append(_issue("flow.object.placeholder.must_not_remain", obj_id or f"flow_objects[{index}]", "对象中存在未解析占位符。"))

    duplicate_ids = sorted(obj_id for obj_id, count in id_counts.items() if count > 1)
    for obj_id in duplicate_ids:
        issues.append(_issue("flow.object.id.unique", obj_id, f"对象 id 重复: {obj_id}。"))

    object_map = {
        str(obj.get("id", "")).strip(): obj
        for obj in dict_objects
        if str(obj.get("id", "")).strip()
    }
    subflow_ids = {
        obj_id
        for obj_id, obj in object_map.items()
        if str(obj.get("type", "")).strip() == "subflow"
    }
    page_ids = {
        obj_id
        for obj_id, obj in object_map.items()
        if str(obj.get("type", "")).strip() == "tab"
    }
    body_nodes_by_subflow: dict[str, list[dict[str, Any]]] = {subflow_id: [] for subflow_id in subflow_ids}

    metrics["page_count"] = len(page_ids)
    metrics["subflow_count"] = len(subflow_ids)

    for obj in dict_objects:
        obj_id = str(obj.get("id", "")).strip()
        obj_type = str(obj.get("type", "")).strip()

        if obj_type == "tab" and not str(obj.get("label", "")).strip():
            issues.append(_issue("flow.tab.label.required", obj_id, "tab 对象必须有 label。"))

        if obj_type == "subflow":
            if not str(obj.get("name", "")).strip():
                issues.append(_issue("flow.subflow.name.required", obj_id, "subflow 对象必须有 name。"))
            for field_name in ("in", "out"):
                if not isinstance(obj.get(field_name), list):
                    issues.append(_issue("flow.subflow.ports.must_be_list", obj_id, f"subflow.{field_name} 必须是列表。"))

        if obj_type.startswith("subflow:"):
            metrics["subflow_instance_count"] += 1
            definition_id = obj_type.split(":", 1)[1]
            definition = object_map.get(definition_id)
            if not definition or definition.get("type") != "subflow":
                issues.append(_issue(
                    "compile.subflow.instance.definition.must_exist",
                    obj_id,
                    f"子流程实例引用了不存在的定义: {definition_id}。",
                ))

        if obj_type not in {"tab", "subflow"}:
            parent_id = str(obj.get("z", "")).strip()
            if parent_id:
                if parent_id not in object_map:
                    issues.append(_issue("flow.object.parent.must_exist", obj_id, f"对象引用了不存在的 z: {parent_id}。"))
                elif parent_id in subflow_ids:
                    body_nodes_by_subflow.setdefault(parent_id, []).append(obj)

            wires = obj.get("wires", [])
            if not isinstance(wires, list):
                issues.append(_issue("flow.wires.must_be_list", obj_id, "wires 必须是列表。"))
            else:
                for group_index, output_group in enumerate(wires):
                    if not isinstance(output_group, list):
                        issues.append(_issue("flow.wire.group.must_be_list", obj_id, "wires 内的每个输出组必须是列表。"))
                        continue
                    for target in output_group:
                        _validate_wire_target(
                            target,
                            object_map=object_map,
                            issues=issues,
                            source_id=obj_id,
                            rule_prefix="flow.wire",
                            group_index=group_index,
                        )

            if obj_type == "quote":
                _validate_quote_reference(obj, object_map, warnings)

    metrics["body_node_count"] = sum(len(nodes) for nodes in body_nodes_by_subflow.values())

    for subflow_id, subflow_obj in [(obj_id, object_map[obj_id]) for obj_id in sorted(subflow_ids)]:
        has_instance = any(
            str(obj.get("type", "")).strip() == f"subflow:{subflow_id}"
            for obj in dict_objects
        )
        allow_empty_body = bool(subflow_obj.get("allow_empty_body", False))
        body_nodes = body_nodes_by_subflow.get(subflow_id, [])
        if has_instance and not body_nodes and not allow_empty_body:
            issues.append(_issue(
                "compile.subflow.body.must_exist",
                subflow_id,
                f"被实例化的 subflow {subflow_id} 必须包含 body 节点。",
            ))

        body_node_ids = {
            str(node.get("id", "")).strip()
            for node in body_nodes
            if str(node.get("id", "")).strip()
        }
        for field_name in ("in", "out"):
            ports = subflow_obj.get(field_name, [])
            if not isinstance(ports, list):
                continue
            for port_index, port in enumerate(ports):
                if not isinstance(port, dict):
                    issues.append(_issue("flow.subflow.port.must_be_dict", subflow_id, f"subflow.{field_name}[{port_index}] 必须是字典。"))
                    continue
                wires = port.get("wires", [])
                if not isinstance(wires, list):
                    issues.append(_issue("flow.subflow.inout.wires.must_be_list", subflow_id, "subflow in/out.wires 必须是列表。"))
                    continue
                for target in wires:
                    target_id = _validate_wire_target(
                        target,
                        object_map=object_map,
                        issues=issues,
                        source_id=subflow_id,
                        rule_prefix="compile.subflow.inout.wire",
                    )
                    if target_id and target_id not in body_node_ids:
                        issues.append(_issue(
                            "compile.subflow.inout.wire.target.must_be_body_node",
                            subflow_id,
                            f"subflow {field_name}.wires 目标 {target_id} 必须挂载在该 subflow body 下。",
                        ))

    _validate_contracts(dict_objects, issues, module_contracts=module_contracts)

    status = "failed" if issues else "passed"
    if not dict_objects:
        warnings.append(_warning("flow.document.empty", "flow_objects", "flow document 为空。"))
    return {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "metrics": metrics,
    }


def _validate_wire_target(
    target: Any,
    *,
    object_map: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    source_id: str,
    rule_prefix: str,
    group_index: int | None = None,
) -> str:
    del group_index
    if not isinstance(target, dict):
        issues.append(_issue(f"{rule_prefix}.target.must_be_dict", source_id, "wire 目标必须是字典。"))
        return ""

    target_id = str(target.get("id", "")).strip()
    if not target_id:
        issues.append(_issue(f"{rule_prefix}.target.id.required", source_id, "wire 目标必须有 id。"))
        return ""
    if target_id not in object_map:
        issues.append(_issue(f"{rule_prefix}.target.must_exist", source_id, f"wire 引用了不存在的目标对象: {target_id}。"))
        return target_id

    target_port = target.get("port", 0)
    if not _is_non_negative_int(target_port):
        issues.append(_issue(f"{rule_prefix}.target.port.non_negative_int", source_id, "wire target.port 必须是非负整数。"))
    return target_id


def _validate_quote_reference(
    obj: dict[str, Any],
    object_map: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    label_name = str(obj.get("labelName", "") or "")
    if not label_name:
        return
    for match in QUOTE_REF_RE.finditer(label_name):
        target_id = match.group(1).strip()
        if target_id and target_id not in object_map:
            warnings.append(_warning(
                "flow.quote.labelName.target.unresolved",
                str(obj.get("id", "") or "quote"),
                f"quote.labelName 引用了当前 flow_objects 中不存在的对象: {target_id}。",
            ))


__all__ = ["validate_flow_document"]
