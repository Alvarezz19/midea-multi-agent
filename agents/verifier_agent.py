"""
Rule-first verifier for phase 1 workflow refactor.

The verifier intentionally focuses on deterministic structural checks so the
first phase can establish trustworthy acceptance before any repair loop is
introduced.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import config
from utils.graph_ir import (
    VerificationIssue,
    VerificationMetrics,
    VerificationReport,
)


class VerifierAgent:
    """Perform deterministic structural validation on IR and compiled output."""

    def _make_issue(
        self,
        issue_id: str,
        scope: str,
        target_id: str,
        rule_id: str,
        message: str,
        suggested_fix: str = "",
        severity: str = "error",
    ) -> VerificationIssue:
        return VerificationIssue(
            issue_id=issue_id,
            severity=severity,
            scope=scope,
            target_id=target_id,
            rule_id=rule_id,
            message=message,
            suggested_fix=suggested_fix,
        )

    def verify(
        self,
        assembled_graph_ir: Dict[str, Any],
        compiled_artifact: Dict[str, Any],
    ) -> Dict[str, Any]:
        issues: List[VerificationIssue] = []
        warnings: List[str] = []
        metrics = VerificationMetrics()

        pages = assembled_graph_ir.get("pages", []) or []
        page_ids = {page.get("page_id") for page in pages if page.get("page_id")}

        subflow_definitions = assembled_graph_ir.get("subflow_definitions", []) or []
        subflow_ids = {
            definition.get("definition_id")
            for definition in subflow_definitions
            if definition.get("definition_id")
        }

        node_instances = assembled_graph_ir.get("node_instances", []) or []
        instance_map = {
            instance.get("instance_id"): instance
            for instance in node_instances
            if instance.get("instance_id")
        }

        for index, instance in enumerate(node_instances, start=1):
            instance_id = instance.get("instance_id", f"instance_{index}")
            page_id = instance.get("page_id")
            subflow_id = instance.get("subflow_id")

            if not page_id and not subflow_id:
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=instance_id,
                    rule_id="ir.node.must_belong_to_scope",
                    message="节点实例必须挂载到 page_id 或 subflow_id。",
                    suggested_fix="在 assembler 中为节点分配页面或子流程作用域。",
                ))

            if page_id and page_id not in page_ids:
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=instance_id,
                    rule_id="ir.node.page.must_exist",
                    message=f"节点引用了不存在的 page_id: {page_id}",
                    suggested_fix="确保 pages 中存在对应页面定义。",
                ))

            if subflow_id and subflow_id not in subflow_ids:
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=instance_id,
                    rule_id="ir.node.subflow.must_exist",
                    message=f"节点引用了不存在的 subflow_id: {subflow_id}",
                    suggested_fix="确保 subflow_definitions 中存在对应子流程定义。",
                ))

        edges = assembled_graph_ir.get("edges", []) or []
        incoming_count: Dict[str, int] = {instance_id: 0 for instance_id in instance_map}
        occupied_input_ports: Dict[str, set[int]] = {
            instance_id: set() for instance_id in instance_map
        }
        for edge in edges:
            edge_id = edge.get("edge_id", f"edge_{len(issues) + 1}")
            from_instance = edge.get("from_instance")
            to_instance = edge.get("to_instance")
            from_port = int(edge.get("from_port", 0) or 0)
            to_port = int(edge.get("to_port", 0) or 0)

            src = instance_map.get(from_instance)
            dst = instance_map.get(to_instance)

            if not src:
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=edge_id,
                    rule_id="ir.edge.source.must_exist",
                    message=f"边引用了不存在的源节点: {from_instance}",
                ))
                continue

            if not dst:
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=edge_id,
                    rule_id="ir.edge.target.must_exist",
                    message=f"边引用了不存在的目标节点: {to_instance}",
                ))
                continue

            src_outputs = int(src.get("output_count", 0) or 0)
            dst_inputs = int(dst.get("input_count", 0) or 0)
            if src_outputs and from_port >= src_outputs:
                metrics.invalid_port_refs += 1
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=edge_id,
                    rule_id="ir.edge.source_port.range",
                    message=f"源端口越界: {from_instance}[{from_port}] / outputs={src_outputs}",
                    suggested_fix="修正 planner 或 assembler 中的端口映射。",
                ))
            if dst_inputs and to_port >= dst_inputs:
                metrics.invalid_port_refs += 1
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=edge_id,
                    rule_id="ir.edge.target_port.range",
                    message=f"目标端口越界: {to_instance}[{to_port}] / inputs={dst_inputs}",
                    suggested_fix="修正 planner 或 assembler 中的端口映射。",
                ))
            incoming_count[to_instance] = incoming_count.get(to_instance, 0) + 1
            if dst_inputs and 0 <= to_port < dst_inputs:
                occupied_input_ports.setdefault(to_instance, set()).add(to_port)

        for instance_id, instance in instance_map.items():
            input_count = int(instance.get("input_count", 0) or 0)
            if input_count <= 0:
                continue

            missing_ports = [
                port_index
                for port_index in range(input_count)
                if port_index not in occupied_input_ports.get(instance_id, set())
            ]
            if missing_ports:
                metrics.missing_required_inputs += len(missing_ports)
                if incoming_count.get(instance_id, 0) == 0:
                    metrics.isolated_nodes += 1
                issues.append(self._make_issue(
                    issue_id=f"IR-{len(issues) + 1:03d}",
                    scope="assembly",
                    target_id=instance_id,
                    rule_id="ir.node.required_inputs.must_be_wired",
                    message=f"节点缺少必需输入端口连线: {missing_ports}",
                    suggested_fix="为每个必需输入端口补齐来源边，或在 assembler 中修正 input_count。",
                ))

        unresolved_items = assembled_graph_ir.get("unresolved_items", []) or []
        for unresolved in unresolved_items:
            warnings.append(unresolved.get("message", "存在未解决项。"))

        raw_json_text = compiled_artifact.get("json_text", "[]")
        flow_objects = compiled_artifact.get("flow_objects", [])
        parsed_json = None
        try:
            parsed_json = json.loads(raw_json_text)
        except Exception as exc:
            issues.append(self._make_issue(
                issue_id=f"CP-{len(issues) + 1:03d}",
                scope="compile",
                target_id="compiled_artifact.json_text",
                rule_id="compile.json.must_parse",
                message=f"编译产物不是合法 JSON: {exc}",
                suggested_fix="检查 compiler 的 JSON 序列化阶段。",
            ))

        if parsed_json is not None and not isinstance(parsed_json, list):
            issues.append(self._make_issue(
                issue_id=f"CP-{len(issues) + 1:03d}",
                scope="compile",
                target_id="compiled_artifact.json_text",
                rule_id="compile.json.must_be_list",
                message="编译产物顶层必须是列表。",
            ))

        if parsed_json is not None and isinstance(parsed_json, list) and len(parsed_json) != len(flow_objects):
            warnings.append("json_text 解析后的对象数量与 flow_objects 长度不一致。")

        object_map = {
            obj.get("id"): obj
            for obj in flow_objects
            if isinstance(obj, dict) and obj.get("id")
        }

        for obj in flow_objects:
            if not isinstance(obj, dict):
                issues.append(self._make_issue(
                    issue_id=f"CP-{len(issues) + 1:03d}",
                    scope="compile",
                    target_id="flow_objects",
                    rule_id="compile.flow_objects.must_be_dict",
                    message="flow_objects 中存在非字典对象。",
                ))
                continue

            obj_id = obj.get("id", "")
            obj_type = obj.get("type", "")
            parent_id = obj.get("z")

            if obj_type not in {"tab", "subflow"} and parent_id and parent_id not in object_map:
                issues.append(self._make_issue(
                    issue_id=f"CP-{len(issues) + 1:03d}",
                    scope="compile",
                    target_id=obj_id or obj_type,
                    rule_id="compile.parent.must_exist",
                    message=f"对象引用了不存在的 z: {parent_id}",
                    suggested_fix="确保 compiler 先生成 tab/subflow，再生成挂载节点。",
                ))

            wires = obj.get("wires", [])
            if not isinstance(wires, list):
                issues.append(self._make_issue(
                    issue_id=f"CP-{len(issues) + 1:03d}",
                    scope="compile",
                    target_id=obj_id or obj_type,
                    rule_id="compile.wires.must_be_list",
                    message="节点 wires 字段必须是列表。",
                ))
                continue

            for output_group in wires:
                if not isinstance(output_group, list):
                    issues.append(self._make_issue(
                        issue_id=f"CP-{len(issues) + 1:03d}",
                        scope="compile",
                        target_id=obj_id or obj_type,
                        rule_id="compile.wire.group.must_be_list",
                        message="wires 内的每个输出组必须是列表。",
                    ))
                    continue

                for target in output_group:
                    if not isinstance(target, dict):
                        issues.append(self._make_issue(
                            issue_id=f"CP-{len(issues) + 1:03d}",
                            scope="compile",
                            target_id=obj_id or obj_type,
                            rule_id="compile.wire.target.must_be_dict",
                            message="wire 目标必须是字典。",
                        ))
                        continue

                    target_id = target.get("id")
                    target_port = int(target.get("port", 0) or 0)
                    target_node = object_map.get(target_id)
                    if not target_node:
                        issues.append(self._make_issue(
                            issue_id=f"CP-{len(issues) + 1:03d}",
                            scope="compile",
                            target_id=obj_id or obj_type,
                            rule_id="compile.wire.target.must_exist",
                            message=f"wire 引用了不存在的目标节点: {target_id}",
                        ))
                        continue

                    target_outputs = int(target_node.get("outputs", 0) or 0)
                    if target_outputs and target_port >= target_outputs:
                        metrics.invalid_port_refs += 1
                        issues.append(self._make_issue(
                            issue_id=f"CP-{len(issues) + 1:03d}",
                            scope="compile",
                            target_id=obj_id or obj_type,
                            rule_id="compile.wire.port.range",
                            message=f"wire 引用了越界端口: {target_id}[{target_port}] / outputs={target_outputs}",
                        ))

        compile_report = compiled_artifact.get("compile_report", {}) or {}
        expected_pages = int(compile_report.get("page_count", 0) or 0)
        expected_subflows = int(compile_report.get("subflow_count", 0) or 0)
        expected_nodes = int(compile_report.get("node_count", 0) or 0)

        actual_pages = sum(1 for obj in flow_objects if isinstance(obj, dict) and obj.get("type") == "tab")
        actual_subflows = sum(1 for obj in flow_objects if isinstance(obj, dict) and obj.get("type") == "subflow")
        actual_nodes = sum(
            1 for obj in flow_objects
            if isinstance(obj, dict) and obj.get("type") not in {"tab", "subflow"}
        )
        if expected_pages and expected_pages != actual_pages:
            warnings.append(f"compile_report.page_count={expected_pages}，实际 tab 数={actual_pages}。")
        if expected_subflows != actual_subflows:
            warnings.append(f"compile_report.subflow_count={expected_subflows}，实际 subflow 数={actual_subflows}。")
        if expected_nodes and expected_nodes != actual_nodes:
            warnings.append(f"compile_report.node_count={expected_nodes}，实际节点数={actual_nodes}。")

        error_issues = [issue for issue in issues if issue.severity == "error"]
        if error_issues:
            scopes = {issue.scope for issue in error_issues}
            repair_scope = "assembly" if "assembly" in scopes else "compile"
            status = "retryable_error"
            issue_summary = f"发现 {len(error_issues)} 个结构错误。"
        else:
            repair_scope = "none"
            status = "passed"
            issue_summary = "结构校验通过。"

        report = VerificationReport(
            status=status,
            repair_scope=repair_scope,
            issue_summary=issue_summary,
            issues=issues,
            warnings=warnings,
            metrics=metrics,
        )

        if config.DEBUG:
            print("\n[VerifierAgent] completed:")
            print(f"   状态: {report.status}")
            print(f"   错误数: {len(error_issues)}")
            print(f"   警告数: {len(report.warnings)}")

        return report.model_dump()

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        assembled_graph_ir = state.get("assembled_graph_ir", {})
        compiled_artifact = state.get("compiled_artifact", {})
        report = self.verify(assembled_graph_ir, compiled_artifact)

        state["verification_report"] = report
        state["current_step"] = "verification_completed"
        state["final_output"] = {
            "json_text": compiled_artifact.get("json_text", ""),
            "compile_report": compiled_artifact.get("compile_report", {}),
            "verification_report": report,
        }
        return state
