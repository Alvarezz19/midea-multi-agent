"""
验证智能体 (Validation Agent)
职责：双重质检 - 形式化验证 + 语义验证
"""
from typing import Dict, List, Any, Tuple
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import json
import config


class ValidationAgent:
    """验证智能体"""
    
    def __init__(self):
        """初始化 LLM（用于语义验证）"""
        # TODO: 实现 LLM 初始化
        # self.llm = ChatOpenAI(
        #     model=config.MODEL_NAME,
        #     openai_api_key=config.OPENAI_API_KEY,
        #     openai_api_base=config.OPENAI_BASE_URL,
        #     temperature=0.2
        # )
        
        self.semantic_prompt = self._create_semantic_prompt()
    
    def _create_semantic_prompt(self) -> ChatPromptTemplate:
        """创建语义验证提示词"""
        template = """你是一位楼宇自控系统的质量检验专家。

原始用户需求：
{user_query}

生成的 JSON 组态：
{generated_json}

请检查生成的组态是否完整实现了用户需求。重点关注：
1. 功能完整性：所有需求点是否都被覆盖？
2. 逻辑正确性：数据流向是否符合控制逻辑？
3. 安全性：是否缺少必要的限值保护、异常处理？
4. 边界条件：极端情况下的行为是否合理？

输出格式（JSON）：
{{
    "passed": true/false,
    "issues": [
        {{
            "severity": "error/warning/info",
            "category": "功能/逻辑/安全/边界",
            "description": "问题描述",
            "suggestion": "修复建议"
        }}
    ],
    "overall_score": 0-100
}}

请开始检验：
"""
        return ChatPromptTemplate.from_template(template)
    
    def formal_validation(self, json_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        形式化验证
        
        Args:
            json_data: 生成的 JSON 组态
            
        Returns:
            (是否通过, 错误列表)
        """
        errors = []
        
        # 1. 检查 JSON 结构完整性
        if "nodes" not in json_data:
            errors.append("缺少 'nodes' 字段")
        if "wires" not in json_data:
            errors.append("缺少 'wires' 字段")
        
        if errors:
            return False, errors
        
        nodes = json_data.get("nodes", [])
        wires = json_data.get("wires", [])
        
        # 2. 检查节点完整性
        node_ids = set()
        for node in nodes:
            if "id" not in node:
                errors.append(f"节点缺少 ID: {node}")
            else:
                node_ids.add(node["id"])
            
            if "type" not in node:
                errors.append(f"节点 {node.get('id')} 缺少 type 字段")
            
            # TODO: 检查节点类型是否在允许列表中
            # TODO: 检查必需参数是否存在
        
        # 3. 检查连线有效性
        for wire in wires:
            source_id = wire.get("source")
            target_id = wire.get("target")
            
            if source_id not in node_ids:
                errors.append(f"连线引用了不存在的源节点: {source_id}")
            
            if target_id not in node_ids:
                errors.append(f"连线引用了不存在的目标节点: {target_id}")
            
            # TODO: 检查端口索引是否有效
        
        # 4. 检查悬空节点（既无输入也无输出）
        connected_nodes = set()
        for wire in wires:
            connected_nodes.add(wire.get("source"))
            connected_nodes.add(wire.get("target"))
        
        dangling_nodes = node_ids - connected_nodes
        if dangling_nodes and len(nodes) > 1:  # 单节点例外
            # 警告而非错误
            errors.append(f"发现悬空节点（可能合理）: {dangling_nodes}")
        
        # 5. 检查循环依赖
        # TODO: 实现拓扑排序检测环路
        
        return len(errors) == 0, errors
    
    def semantic_validation(self, user_query: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        语义验证（由 LLM 执行）
        
        Args:
            user_query: 原始用户需求
            json_data: 生成的 JSON
            
        Returns:
            验证报告
        """
        # TODO: 调用 LLM 进行语义分析
        # messages = self.semantic_prompt.format_messages(
        #     user_query=user_query,
        #     generated_json=json.dumps(json_data, indent=2, ensure_ascii=False)
        # )
        # response = self.llm(messages)
        # report = json.loads(response.content)
        
        # 示例报告（硬编码）
        report = {
            "passed": True,
            "issues": [
                {
                    "severity": "warning",
                    "category": "安全",
                    "description": "未检测到温度传感器故障保护逻辑",
                    "suggestion": "建议添加传感器异常时的默认策略"
                },
                {
                    "severity": "info",
                    "category": "功能",
                    "description": "手自动切换逻辑已实现",
                    "suggestion": "符合需求"
                }
            ],
            "overall_score": 85
        }
        
        return report
    
    def validate(self, user_query: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        完整验证流程
        
        Args:
            user_query: 用户需求
            json_data: 生成的 JSON
            
        Returns:
            综合验证结果
        """
        # 1. 形式化验证
        formal_passed, formal_errors = self.formal_validation(json_data)
        
        # 2. 语义验证（仅在形式化通过时执行）
        semantic_report = {}
        if formal_passed:
            semantic_report = self.semantic_validation(user_query, json_data)
        
        # 综合结果
        result = {
            "passed": formal_passed and semantic_report.get("passed", False),
            "formal_validation": {
                "passed": formal_passed,
                "errors": formal_errors
            },
            "semantic_validation": semantic_report,
            "timestamp": "2024-01-01T00:00:00Z"  # TODO: 添加真实时间戳
        }
        
        return result
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        user_query = state.get("user_query", "")
        execution_result = state.get("execution_result", {})
        
        # 提取生成的 JSON（可能在 stdout 或 result 字段）
        json_data = execution_result.get("result", {})
        
        # 执行验证
        validation_result = self.validate(user_query, json_data)
        
        # 更新状态
        state["validation_result"] = validation_result
        state["current_step"] = "validation_completed"
        
        return state
