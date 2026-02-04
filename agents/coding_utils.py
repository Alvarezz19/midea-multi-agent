"""
编码智能体辅助工具
包含 ID 生成、拓扑布局等功能
"""
import uuid
from typing import List, Dict, Any, Tuple


def generate_short_uuid() -> str:
    """生成类似 'b45d2af' 的短ID（7位）"""
    return str(uuid.uuid4()).replace('-', '')[:7]


def topological_layout(nodes: List[Dict], connections: List[Dict]) -> Dict[str, Dict[str, int]]:
    """
    计算节点的 (x, y) 坐标
    
    策略：
    1. 构建邻接表
    2. 计算每个节点的深度（层级）使用拓扑排序
    3. 根据层级分配 X，根据层内顺序分配 Y
    
    Args:
        nodes: 节点列表，每个节点包含 logic_id
        connections: 连接列表，包含 from_node, to_node
        
    Returns:
        字典，key 为 logic_id，value 为 {x: int, y: int}
    """
    if not nodes:
        return {}
    
    # 1. 构建图结构
    adj_list = {node['logic_id']: [] for node in nodes}
    in_degree = {node['logic_id']: 0 for node in nodes}
    
    for conn in connections:
        src = conn['from_node']
        dst = conn['to_node']
        if src in adj_list and dst in in_degree:
            adj_list[src].append(dst)
            in_degree[dst] += 1
    
    # 2. 拓扑排序计算层级 (BFS)
    levels = {}  # logic_id -> level
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    
    # 初始化 layer 0（输入节点）
    for nid in queue:
        levels[nid] = 0
    
    # BFS 遍历
    while queue:
        u = queue.pop(0)
        current_level = levels[u]
        
        for v in adj_list[u]:
            # 下游节点的层级 = max(已有层级, 上游层级 + 1)
            levels[v] = max(levels.get(v, 0), current_level + 1)
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
    
    # 处理没有连接的孤立节点（如果有）
    for nid in adj_list.keys():
        if nid not in levels:
            levels[nid] = 0
    
    # 3. 分配坐标
    # 配置参数
    START_X, START_Y = 100, 100
    X_GAP, Y_GAP = 200, 80  # 模块间的间距
    
    # 按层级分组
    level_groups = {}
    for nid, lvl in levels.items():
        if lvl not in level_groups:
            level_groups[lvl] = []
        level_groups[lvl].append(nid)
    
    coordinates = {}
    
    # 遍历每一层
    max_level = max(levels.values()) if levels else 0
    for lvl in range(max_level + 1):
        group = level_groups.get(lvl, [])
        for index, nid in enumerate(group):
            x = START_X + (lvl * X_GAP)
            y = START_Y + (index * Y_GAP)
            coordinates[nid] = {"x": x, "y": y}
    
    return coordinates


def build_reverse_connections(connections: List[Dict], id_map: Dict[str, str]) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """
    构建反向连接索引（用于填充 wires 字段）
    
    平台的 wires 格式：
    wires[input_port_index] = [{"id": upstream_uuid, "port": upstream_output_port}]
    
    即：wires 记录的是当前节点的每个输入端口连接到哪个上游节点的输出端口。
    
    Args:
        connections: 规划智能体的连接列表
        id_map: logic_id -> real_uuid 的映射
        
    Returns:
        字典结构: {
            target_logic_id: {
                input_port_index: {"id": source_uuid, "port": source_port_index}
            }
        }
    """
    reverse_map = {}
    
    for conn in connections:
        target_logic_id = conn['to_node']
        input_port = conn['to_port_index']
        source_logic_id = conn['from_node']
        output_port = conn['from_port_index']
        
        if target_logic_id not in reverse_map:
            reverse_map[target_logic_id] = {}
        
        # 记录连接信息
        reverse_map[target_logic_id][input_port] = {
            "id": id_map.get(source_logic_id, "unknown"),
            "port": output_port
        }
    
    return reverse_map


def fill_template(template: Dict[str, Any], 
                  node: Dict[str, Any],
                  real_id: str,
                  flow_id: str,
                  coords: Dict[str, int],
                  wires: List[List[Dict]],
                  module_name: str = "") -> Dict[str, Any]:
    """
    填充模板，替换占位符并注入参数
    
    Args:
        template: 从 schema 获取的 template_json
        node: PlanIR 中的节点信息
        real_id: 生成的真实 UUID
        flow_id: 流程 ID
        coords: 坐标信息 {x, y}
        wires: 构建好的 wires 数组
        module_name: 模块原始名称（如"加法运算"）
        
    Returns:
        填充后的完整节点 JSON
    """
    import copy
    result = copy.deepcopy(template)
    
    # 1. 替换基础占位符
    result['id'] = real_id
    result['z'] = flow_id
    result['x'] = coords['x']
    result['y'] = coords['y']
    result['wires'] = wires
    
    # 2. 注入规划参数
    planned_params = node.get('parameters', {})
    
    for key, value in planned_params.items():
        # 特殊处理：inputCount -> inputs
        if key == "inputCount" and "inputs" in result:
            result["inputs"] = value
        else:
            result[key] = value
    
    # 3. 处理 name 字段
    if 'name' in result:
        # 优先使用规划参数中的 name，其次使用模块原始名称
        if 'name' not in planned_params:
            result['name'] = module_name if module_name else result.get('type', '未命名')
            # result['name'] = node.get('reasoning', result.get('type', '未命名'))[:50]
    
    # 4. 清理占位符（删除未替换的模板变量）
    clean_placeholders(result)
    
    return result


def clean_placeholders(obj: Any) -> None:
    """递归清理包含 {{}} 占位符的字段"""
    if isinstance(obj, dict):
        keys_to_delete = []
        for k, v in obj.items():
            if isinstance(v, str) and '{{' in v and '}}' in v:
                # 标记删除未替换的占位符字段
                keys_to_delete.append(k)
            elif isinstance(v, (dict, list)):
                clean_placeholders(v)
        # 删除占位符字段
        for k in keys_to_delete:
            del obj[k]
    elif isinstance(obj, list):
        for item in obj:
            clean_placeholders(item)
