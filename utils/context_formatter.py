"""
上下文格式化工具
用于将检索结果转换为不同智能体所需的格式
"""
from typing import Dict, Any, List


def _port_label(port: Dict[str, Any]) -> str:
    return port.get('label') or port.get('name') or '未命名'


def _summarize_port_overview(ports_def: Dict[str, Any]) -> str:
    input_ports = ports_def.get('inputs', [])
    output_ports = ports_def.get('outputs', [])
    return f"{len(input_ports)}入 -> {len(output_ports)}出"


def _summarize_param_keys(params_schema: Dict[str, Any]) -> str:
    if not params_schema:
        return "无"
    return ', '.join(params_schema.keys())


def _append_detail_block(lines: List[str], node: Dict[str, Any]) -> None:
    params_schema = node.get('parameters_schema', {})
    if params_schema:
        lines.append("    参数定义:")
        for key, info in params_schema.items():
            p_type = info.get('type', 'unknown')
            p_default = info.get('default', 'N/A')
            p_desc = info.get('description', '')
            constraint_parts = []
            if 'minimum' in info:
                constraint_parts.append(f"最小={info['minimum']}")
            if 'maximum' in info:
                constraint_parts.append(f"最大={info['maximum']}")
            if 'enum' in info:
                constraint_parts.append(f"可选={info['enum']}")
            constraint_str = f" [{', '.join(constraint_parts)}]" if constraint_parts else ""
            lines.append(f"       • {key} ({p_type}, 默认={p_default}){constraint_str}: {p_desc}")

    ports_def = node.get('ports_definition', {})
    if ports_def:
        input_ports = ports_def.get('inputs', [])
        output_ports = ports_def.get('outputs', [])
        if input_ports:
            lines.append("    输入端口:")
            for port in input_ports:
                p_idx = port.get('index', 0)
                p_label = _port_label(port)
                p_type = port.get('type', 'any')
                p_desc = port.get('description', '')
                p_cond = port.get('condition', 'always')
                cond_str = f" (条件: {p_cond})" if p_cond != 'always' else ""
                lines.append(f"       [{p_idx}] {p_label} ({p_type}){cond_str}: {p_desc}")
        if output_ports:
            lines.append("    输出端口:")
            for port in output_ports:
                p_idx = port.get('index', 0)
                p_label = _port_label(port)
                p_type = port.get('type', 'any')
                p_desc = port.get('description', '')
                p_cond = port.get('condition', 'always')
                cond_str = f" (条件: {p_cond})" if p_cond != 'always' else ""
                lines.append(f"       [{p_idx}] {p_label} ({p_type}){cond_str}: {p_desc}")

    usage_guides = node.get('usage_guides', [])
    if usage_guides:
        lines.append("    适用场景:")
        for guide in usage_guides:
            lines.append(f"       • {guide}")


def _append_summary_block(lines: List[str], node: Dict[str, Any]) -> None:
    params_schema = node.get('parameters_schema', {})
    ports_def = node.get('ports_definition', {})
    description = node.get('description', '无描述')
    lines.append(f"    功能: {description}")
    lines.append(f"    参数键名: {_summarize_param_keys(params_schema)}")
    lines.append(f"    端口概览: {_summarize_port_overview(ports_def)}")


def format_docs_for_planner(
    retrieval_context: Dict[str, Any],
    detail_top_n: int = 5,
    max_modules: int = 8,
) -> str:
    """
    将检索智能体返回的完整上下文格式化为规划智能体友好的文本格式
    
    核心策略：
    - 剔除大块模板数据（template_json、keywords 完整列表）
    - 保留规划决策所需的关键信息（功能描述、使用场景、分类）
    - 保留精简的参数定义（键名、类型、默认值）和端口定义（索引、标签、类型）
    - 格式化为结构化的自然语言文本，便于 LLM 理解
    
    Args:
        retrieval_context: 检索智能体返回的完整上下文字典
        detail_top_n: 前 N 个模块输出详细信息，其余输出摘要信息
        max_modules: 最多传递给规划智能体的模块数量
        
    Returns:
        格式化后的字符串，适合作为规划智能体的输入
    """
    if not retrieval_context or not retrieval_context.get('relevant_nodes'):
        return "⚠️ 未找到相关模块，请重新描述需求或调整检索策略。"
    
    lines = []
    
    # ========== 标题部分 ==========
    # lines.append("=" * 80)
    lines.append("知识库检索结果")
    # lines.append("=" * 80)
    
    # ========== 检索元信息 ==========
    metadata = retrieval_context.get('metadata', {})
    lines.append(f"\n检索查询: {retrieval_context.get('query', 'N/A')}")
    lines.append(f"检索统计:")
    lines.append(f"   - 找到模块数: {metadata.get('retrieved_count', 0)}")
    lines.append(f"   - 平均相似度: {metadata.get('avg_confidence_score', 0):.3f}")
    
    if metadata.get('detected_operations'):
        lines.append(f"   - 检测到的运算类型: {', '.join(metadata['detected_operations'])}")
    
    if metadata.get('intent'):
        lines.append(f"   - 推测意图: {metadata['intent']}")
    
    lines.append("")
    
    # ========== 相关模块列表 ==========
    lines.append("相关模块清单:")
    # lines.append("-" * 80)
    
    relevant_nodes = retrieval_context.get('relevant_nodes', [])[:max_modules]
    
    for index, node in enumerate(relevant_nodes, start=1):
        rank = node.get('rank', 0)
        name = node.get('name', 'Unknown')
        module_type = node.get('module_type', 'Unknown')
        category = node.get('category', 'Unknown')
        similarity = node.get('similarity_score', 0)
        
        # 模块标题
        lines.append(f"\n[{rank}] {name}")
        lines.append(f"    类型: {module_type}")
        lines.append(f"    分类: {category}")
        lines.append(f"    相似度: {similarity:.3f}")

        if index <= detail_top_n:
            _append_detail_block(lines, node)
        else:
            _append_summary_block(lines, node)
        
        # 如果有匹配的查询变体（多查询策略）
        matched_query = node.get('matched_query')
        if matched_query and matched_query != retrieval_context.get('query'):
            lines.append(f"    匹配查询: {matched_query}")
        
        lines.append("")  # 模块之间的分隔
    
    # ========== 总结建议 ==========
    # lines.append("-" * 80)
    lines.append("规划建议:")
    
    # 根据相似度给出建议
    top_similarity = relevant_nodes[0].get('similarity_score', 0) if relevant_nodes else 0
    
    if top_similarity > 0.8:
        lines.append("   发现高度匹配的模块，建议优先使用排名靠前的模块。")
    elif top_similarity > 0.6:
        lines.append("   匹配度中等，建议结合多个模块或适当调整参数。")
    else:
        lines.append("   匹配度较低，可能需要组合多个基础模块实现需求。")
    
    # 分类统计
    categories = {}
    for node in relevant_nodes:
        cat = node.get('category', 'Unknown').split('/')[0]
        categories[cat] = categories.get(cat, 0) + 1
    
    if categories:
        cat_summary = ', '.join([f"{k}({v}个)" for k, v in categories.items()])
        lines.append(f"   模块分类分布: {cat_summary}")
    
    # lines.append("=" * 80)
    
    return "\n".join(lines)


def format_docs_for_coding(retrieval_context: Dict[str, Any], 
                          selected_modules: List[str]) -> str:
    """
    为编码智能体准备详细的模块信息
    
    在规划智能体确定需要使用哪些模块后，此函数提取这些模块的完整技术细节
    
    Args:
        retrieval_context: 检索智能体返回的完整上下文
        selected_modules: 规划智能体选定的模块类型列表
        
    Returns:
        包含完整技术细节的格式化文本
    """
    if not retrieval_context or not retrieval_context.get('relevant_nodes'):
        return "⚠️ 未找到相关模块信息"
    
    lines = []
    lines.append("=" * 80)
    lines.append("🔧 模块技术规格")
    lines.append("=" * 80)
    
    relevant_nodes = retrieval_context.get('relevant_nodes', [])
    
    for module_type in selected_modules:
        # 查找对应的模块信息
        module_info = None
        for node in relevant_nodes:
            if node.get('module_type') == module_type:
                module_info = node
                break
        
        if not module_info:
            lines.append(f"\n⚠️  未找到模块: {module_type}")
            continue
        
        lines.append(f"\n{'=' * 80}")
        lines.append(f"模块: {module_info.get('name')} ({module_type})")
        lines.append(f"{'=' * 80}")
        
        # 基本信息
        lines.append(f"\n📝 描述: {module_info.get('description', '无')}")
        lines.append(f"📂 分类: {module_info.get('category', '无')}")
        
        # 参数定义
        params_schema = module_info.get('parameters_schema', {})
        if params_schema:
            lines.append(f"\n⚙️  参数定义:")
            for key, info in params_schema.items():
                # 跳过坐标等技术字段
                if key in ['x', 'y', 'wires', 'id', 'z']:
                    continue
                
                param_type = info.get('type', 'unknown')
                param_desc = info.get('description', '无描述')
                param_default = info.get('default', 'N/A')
                param_required = info.get('required', False)
                
                lines.append(f"\n   [{key}] ({param_type})")
                lines.append(f"      描述: {param_desc}")
                lines.append(f"      默认值: {param_default}")
                lines.append(f"      必填: {'是' if param_required else '否'}")
                
                # 枚举值
                if 'enum' in info:
                    lines.append(f"      可选值: {info['enum']}")
                
                # 约束条件
                if 'minimum' in info or 'maximum' in info:
                    constraints = []
                    if 'minimum' in info:
                        constraints.append(f"最小值={info['minimum']}")
                    if 'maximum' in info:
                        constraints.append(f"最大值={info['maximum']}")
                    lines.append(f"      约束: {', '.join(constraints)}")
        
        # 端口定义
        ports_def = module_info.get('ports_definition', {})
        if ports_def:
            lines.append(f"\n🔌 端口定义:")
            
            # 输入端口
            inputs = ports_def.get('inputs', [])
            if inputs:
                lines.append(f"\n   输入端口:")
                for inp in inputs:
                    label = inp.get('label', '未命名')
                    desc = inp.get('description', '无描述')
                    port_type = inp.get('type', 'any')
                    condition = inp.get('condition', 'always')
                    
                    lines.append(f"\n      • {label} ({port_type})")
                    lines.append(f"        {desc}")
                    if condition != 'always':
                        lines.append(f"        条件: {condition}")
            
            # 输出端口
            outputs = ports_def.get('outputs', [])
            if outputs:
                lines.append(f"\n   输出端口:")
                for out in outputs:
                    label = out.get('label', '未命名')
                    desc = out.get('description', '无描述')
                    port_type = out.get('type', 'any')
                    condition = out.get('condition', 'always')
                    
                    lines.append(f"\n      • {label} ({port_type})")
                    lines.append(f"        {desc}")
                    if condition != 'always':
                        lines.append(f"        条件: {condition}")
        
        # 模板JSON（用于代码生成）
        template = module_info.get('template_json', {})
        if template:
            lines.append(f"\n📋 节点模板:")
            import json
            lines.append(f"```json")
            lines.append(json.dumps(template, ensure_ascii=False, indent=2))
            lines.append(f"```")
    
    lines.append(f"\n{'=' * 80}")
    
    return "\n".join(lines)


def get_module_summary(retrieval_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    提取检索结果的结构化摘要
    
    Args:
        retrieval_context: 检索智能体返回的完整上下文
        
    Returns:
        结构化的摘要信息
    """
    relevant_nodes = retrieval_context.get('relevant_nodes', [])
    
    summary = {
        "total_modules": len(relevant_nodes),
        "module_types": [node.get('module_type') for node in relevant_nodes],
        "top_module": relevant_nodes[0] if relevant_nodes else None,
        "avg_similarity": retrieval_context.get('metadata', {}).get('avg_confidence_score', 0),
        "categories": list(set(
            node.get('category', '').split('/')[0] 
            for node in relevant_nodes 
            if node.get('category')
        ))
    }
    
    return summary
