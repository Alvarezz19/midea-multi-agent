"""
Kong CUBE SDK - 组态代码生成器
用于将 Python 代码转换为 KONG CUBE JSON 组态文件
"""
import uuid
from typing import Dict, List, Any, Optional


class KongNode:
    """代表一个功能块节点"""
    
    def __init__(self, node_type: str, name: str, **params):
        """
        初始化节点
        
        Args:
            node_type: 节点类型，如 'swInput', 'compare', 'switch' 等
            name: 节点名称
            **params: 节点参数
        """
        self.id = str(uuid.uuid4())
        self.type = node_type
        self.name = name
        self.params = params
        self.wires: List[Dict] = []  # 连线数组
        self.x = 0  # 坐标将由自动布局算法计算
        self.y = 0
    
    def connect(self, target_node: 'KongNode', out_port: int = 0, in_port: int = 0):
        """
        建立与目标节点的连接
        
        Args:
            target_node: 目标节点
            out_port: 输出端口索引
            in_port: 输入端口索引
        """
        # TODO: 添加端口有效性检查
        # TODO: 检查是否存在循环依赖
        
        wire = {
            "source": self.id,
            "sourcePort": out_port,
            "target": target_node.id,
            "targetPort": in_port
        }
        self.wires.append(wire)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "wires": self.wires,
            **self.params
        }


class FlowBuilder:
    """画布管理器"""
    
    def __init__(self):
        self.nodes: List[KongNode] = []
    
    def add_node(self, node_type: str, name: str, **params) -> KongNode:
        """
        添加节点到画布
        
        Args:
            node_type: 节点类型
            name: 节点名称
            **params: 节点参数
            
        Returns:
            创建的节点对象
        """
        node = KongNode(node_type, name, **params)
        self.nodes.append(node)
        return node
    
    def auto_layout(self):
        """
        自动布局算法
        TODO: 实现层次化布局算法
        - 拓扑排序确定层级
        - 每层节点均匀分布
        - 避免连线交叉
        """
        # 简单实现：垂直排列
        y_offset = 100
        for i, node in enumerate(self.nodes):
            node.x = 200
            node.y = y_offset + i * 150
    
    def validate(self) -> tuple[bool, List[str]]:
        """
        验证流程图的合法性
        
        Returns:
            (是否合法, 错误信息列表)
        """
        errors = []
        
        # TODO: 检查悬空节点（无输入也无输出）
        # TODO: 检查端口类型是否匹配
        # TODO: 检查是否存在循环依赖
        
        return len(errors) == 0, errors
    
    def export_json(self) -> Dict[str, Any]:
        """
        导出为 KONG CUBE 标准 JSON 格式
        
        Returns:
            JSON 字典
        """
        self.auto_layout()
        
        # 收集所有连线
        all_wires = []
        for node in self.nodes:
            all_wires.extend(node.wires)
        
        return {
            "version": "1.0",
            "nodes": [node.to_dict() for node in self.nodes],
            "wires": all_wires
        }


# 预定义的常用节点类型（用于代码生成时的提示）
NODE_TYPES = {
    "swInput": "模拟量输入",
    "compare": "比较模块",
    "switch": "切换模块",
    "math": "数学运算",
    "logic": "逻辑运算",
    "timer": "定时器",
    "accumulator": "累计器"
}
