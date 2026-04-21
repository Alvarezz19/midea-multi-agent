"""
编码智能体 (Coding Agent)
职责：将规划方案转化为平台可执行的 JSON 配置文件
"""
from typing import Dict, List, Any
import json
import copy
import config
from .coding_utils import (
    generate_short_uuid,
    topological_layout,
    build_reverse_connections,
    fill_template,
    resolve_input_count
)


class CodingAgent:
    """编码智能体 - 将规划图转换为平台 JSON 配置"""
    
    def __init__(self):
        """初始化编码智能体"""
        if config.DEBUG:
            print(f"✅ 编码智能体初始化完成")
    
    def generate_json(self, plan_ir: Dict[str, Any], retrieval_context: Dict[str, Any]) -> str:
        """
        生成最终的 JSON 配置文件
        
        Args:
            plan_ir: 规划智能体输出的 PlanIR 字典
            retrieval_context: 检索智能体返回的完整上下文（包含 template_json）
            
        Returns:
            JSON 字符串
        """
        if config.DEBUG:
            print(f"\n🔧 编码智能体开始工作...")
            print(f"   目标: {plan_ir.get('goal', 'N/A')}")
            print(f"   节点数: {len(plan_ir.get('nodes', []))}")
        
        try:
            # --- 步骤1: 建立模块索引 ---
            relevant_nodes = retrieval_context.get('relevant_nodes', [])
            doc_map = {node['module_type']: node for node in relevant_nodes}
            
            if config.DEBUG:
                print(f"\n   📚 可用模块类型: {list(doc_map.keys())}")
            
            # --- 步骤2: ID 实例化 ---
            id_map = {}
            nodes = plan_ir.get('nodes', [])
            for node in nodes:
                id_map[node['logic_id']] = generate_short_uuid()
            
            if config.DEBUG:
                print(f"\n   🔑 ID 映射:")
                for logic_id, real_id in list(id_map.items())[:3]:
                    print(f"      {logic_id} -> {real_id}")
                if len(id_map) > 3:
                    print(f"      ... 共 {len(id_map)} 个")
            
            # --- 步骤3: 自动布局 ---
            connections = plan_ir.get('connections', [])
            coords_map = topological_layout(nodes, connections)
            
            if config.DEBUG:
                print(f"\n   📐 布局完成: {len(coords_map)} 个节点定位")
            
            # --- 步骤4: 反向连线索引 ---
            # 平台的 wires 格式是：wires[输入端口索引] = [{id: 上游节点ID, port: 上游输出端口}]
            reverse_connections = build_reverse_connections(connections, id_map)
            
            if config.DEBUG:
                print(f"\n   🔗 连接关系: {len(connections)} 条")
            
            # --- 步骤5: 生成节点 JSON ---
            final_modules = []
            
            # 首先添加 Tab 页（容器）
            flow_id = generate_short_uuid()
            final_modules.append({
                "id": flow_id,
                "type": "tab",
                "label": "自动生成流程",
                "disabled": False,
                "info": ""
            })
            
            # 逐个生成节点
            for node in nodes:
                logic_id = node['logic_id']
                module_type = node['module_type']
                
                # A. 获取模板
                if module_type not in doc_map:
                    if config.DEBUG:
                        print(f"   ⚠️  警告: 缺少模块 {module_type} 的定义，跳过")
                    continue
                
                module_doc = doc_map[module_type]
                template_raw = module_doc.get('template_json', {})
                
                # 处理 template_json 可能是列表的情况
                if isinstance(template_raw, list):
                    if len(template_raw) > 0:
                        template = copy.deepcopy(template_raw[0])
                    else:
                        template = {}
                else:
                    template = copy.deepcopy(template_raw)
                
                # B. 确定输入端口数量
                planned_params = node.get('parameters', {})
                template_inputs = template.get('inputs', 0)
                input_count = resolve_input_count(
                    template_inputs, planned_params, module_doc
                )
                
                # C. 构建 wires 数组（基于输入端口）
                # wires[输入端口索引] = [{id: 上游节点ID, port: 上游输出端口}]
                wires = []
                node_incoming = reverse_connections.get(logic_id, {})
                
                for i in range(input_count):
                    if i in node_incoming:
                        # 存在连接
                        conn_info = node_incoming[i]
                        wires.append([conn_info])  # 注意：数组的数组
                    else:
                        # 悬空端口
                        wires.append([])
                
                # D. 填充模板
                real_id = id_map[logic_id]
                coords = coords_map.get(logic_id, {'x': 0, 'y': 0})
                module_name = module_doc.get('name', module_type)  # 获取模块原始名称
                
                filled_node = fill_template(
                    template=template,
                    node=node,
                    real_id=real_id,
                    flow_id=flow_id,
                    coords=coords,
                    wires=wires,
                    module_name=module_name
                )
                
                final_modules.append(filled_node)
            
            # --- 步骤6: 序列化 ---
            json_output = json.dumps(final_modules, indent=2, ensure_ascii=False)
            
            if config.DEBUG:
                print(f"\n✅ JSON 生成完成:")
                print(f"   总节点数: {len(final_modules)} (含 Tab 页)")
                print(f"   文件大小: {len(json_output)} 字符")
            
            return json_output
        
        except Exception as e:
            if config.DEBUG:
                print(f"\n❌ 编码失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 返回空配置
            return json.dumps([{
                "id": generate_short_uuid(),
                "type": "tab",
                "label": "生成失败",
                "disabled": True,
                "info": str(e)
            }], indent=2, ensure_ascii=False)
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        execution_plan = state.get("execution_plan", {})
        retrieval_context = state.get("retrieval_context", {})
        
        # 生成 JSON 配置
        json_output = self.generate_json(execution_plan, retrieval_context)
        
        # 更新状态
        state["generated_code"] = json_output  # 这里存储的是 JSON 字符串
        state["current_step"] = "coding_completed"
        
        return state
