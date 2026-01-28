"""
查询预处理器
用于优化和增强用户查询，提高检索准确率
"""
import re
from typing import List, Dict, Any


class QueryProcessor:
    """查询预处理器"""
    
    # 数学运算符号映射
    MATH_OPERATORS = {
        '+': '加法',
        '-': '减法',
        '×': '乘法',
        '*': '乘法',
        '÷': '除法',
        '/': '除法',
        '%': '模运算',
        '^': '幂运算',
        '**': '幂运算',
    }
    
    # 关键词模式
    KEYWORD_PATTERNS = {
        'comparison': r'(比较|大于|小于|等于|>=|<=|==|>|<)',
        'logic': r'(与|或|非|且|AND|OR|NOT|逻辑)',
        'timing': r'(定时|延时|延迟|计时|timer|delay)',
        'statistics': r'(平均值|最大值|最小值|求和|统计)',
        'conversion': r'(转换|变换|映射|线性)',
    }
    
    # 变量相关的模式（表示需要输入的量）
    VARIABLE_PATTERNS = [
        r'(温度|压力|流量|湿度|速度|功率|电压|电流|频率)',  # 物理量
        r'(设定值|测量值|反馈值|目标值|实际值)',  # 控制量
        r'(传感器|探头|仪表|监测)',  # 数据源
        r'[\u4e00-\u9fa5]+值',  # xx值
    ]
    
    # 常量相关的模式（表示固定参数）
    CONSTANT_PATTERNS = [
        r'\d+\.?\d*',  # 数字（整数或小数）
        r'(系数|参数|常数|倍数|比例)',
    ]
    
    @staticmethod
    def detect_variables(query: str) -> bool:
        """
        检测查询中是否包含变量相关的模式
        
        Args:
            query: 用户查询
            
        Returns:
            是否包含变量模式
        """
        for pattern in QueryProcessor.VARIABLE_PATTERNS:
            if re.search(pattern, query):
                return True
        return False
    
    @staticmethod
    def detect_constants(query: str) -> bool:
        """
        检测查询中是否包含常量（数字）
        
        Args:
            query: 用户查询
            
        Returns:
            是否包含常量
        """
        # 查找数字
        return bool(re.search(r'\d+\.?\d*', query))
    
    @staticmethod
    def detect_math_operations(query: str) -> List[str]:
        """
        检测查询中的数学运算符号
        
        Args:
            query: 用户查询
            
        Returns:
            检测到的运算类型列表
        """
        operations = []
        
        for symbol, operation in QueryProcessor.MATH_OPERATORS.items():
            if symbol in query:
                operations.append(operation)
        
        # 去重
        return list(set(operations))
    
    @staticmethod
    def detect_keywords(query: str) -> Dict[str, bool]:
        """
        检测查询中的关键词模式
        
        Args:
            query: 用户查询
            
        Returns:
            检测到的模式字典
        """
        patterns = {}
        
        for pattern_name, pattern in QueryProcessor.KEYWORD_PATTERNS.items():
            patterns[pattern_name] = bool(re.search(pattern, query))
        
        return patterns
    
    @staticmethod
    def enhance_query(query: str) -> Dict[str, Any]:
        """
        增强查询，提取关键信息并生成优化的查询变体
        
        Args:
            query: 原始用户查询
            
        Returns:
            增强后的查询信息
        """
        # 检测数学运算
        math_ops = QueryProcessor.detect_math_operations(query)
        
        # 检测关键词模式
        keyword_patterns = QueryProcessor.detect_keywords(query)
        
        # 检测变量和常量
        has_variables = QueryProcessor.detect_variables(query)
        has_constants = QueryProcessor.detect_constants(query)
        
        # 生成查询变体
        query_variants = [query]  # 保留原始查询
        
        # 如果检测到数学运算，生成运算相关的查询
        if math_ops:
            # 添加运算关键词
            ops_query = ' '.join(math_ops) + ' 运算'
            query_variants.append(ops_query)
            
            # 如果有公式，提取公式核心
            if '公式' in query or '=' in query:
                formula_query = f"数学运算 {' '.join(math_ops)}"
                query_variants.append(formula_query)
        
        # 如果检测到变量模式，添加变量相关查询
        if has_variables:
            query_variants.append('变量 输入 数据')
            if '温度' in query or '压力' in query or '流量' in query:
                query_variants.append('传感器 测量值 变量')
        
        # 如果检测到常量（数字），添加常量相关查询
        if has_constants and (math_ops or '公式' in query):
            query_variants.append('常量 固定值 参数')
        
        # 基于检测到的模式生成查询
        if keyword_patterns.get('comparison'):
            query_variants.append('比较判断')
        
        if keyword_patterns.get('logic'):
            query_variants.append('逻辑运算')
        
        if keyword_patterns.get('timing'):
            query_variants.append('定时器 延时')
        
        if keyword_patterns.get('statistics'):
            query_variants.append('统计运算')
        
        # 提取查询意图
        intent = QueryProcessor._infer_intent(query, math_ops, keyword_patterns, has_variables, has_constants)
        
        return {
            'original_query': query,
            'query_variants': query_variants,
            'detected_operations': math_ops,
            'keyword_patterns': keyword_patterns,
            'has_variables': has_variables,
            'has_constants': has_constants,
            'intent': intent
        }
    
    @staticmethod
    def _infer_intent(query: str, math_ops: List[str], patterns: Dict[str, bool],
                     has_variables: bool = False, has_constants: bool = False) -> str:
        """
        推断查询意图
        
        Args:
            query: 查询文本
            math_ops: 检测到的数学运算
            patterns: 检测到的模式
            has_variables: 是否包含变量
            has_constants: 是否包含常量
            
        Returns:
            意图描述
        """
        if math_ops:
            return 'mathematical_computation'
        elif patterns.get('comparison'):
            return 'comparison'
        elif patterns.get('logic'):
            return 'logic_operation'
        elif patterns.get('timing'):
            return 'timing_control'
        elif patterns.get('statistics'):
            return 'statistical_analysis'
        elif has_variables:
            return 'variable_input'
        else:
            return 'general_query'
    
    @staticmethod
    def should_use_multi_query(query: str) -> bool:
        """
        判断是否应该使用多查询策略
        
        Args:
            query: 用户查询
            
        Returns:
            是否使用多查询
        """
        # 如果查询很长，或包含公式，或包含多个运算符号
        if len(query) > 30:
            return True
        
        math_ops = QueryProcessor.detect_math_operations(query)
        if len(math_ops) > 1:
            return True
        
        return False
