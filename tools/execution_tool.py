"""
执行工具节点 (Execution Tool)
职责：代码沙箱，执行生成的 Python 代码并捕获输出
"""
import sys
import io
import traceback
from typing import Dict, Any
import json


class ExecutionTool:
    """代码执行沙箱（非 AI 节点）"""
    
    def __init__(self):
        """初始化执行环境"""
        self.timeout = 10  # 执行超时时间（秒）
    
    def execute_code(self, code: str) -> Dict[str, Any]:
        """
        在隔离环境中执行 Python 代码
        
        Args:
            code: Python 代码字符串
            
        Returns:
            执行结果字典
        """
        result = {
            "success": False,
            "result": None,
            "stdout": "",
            "stderr": "",
            "error": None
        }
        
        # 重定向标准输出和标准错误
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            # 准备执行环境
            global_namespace = {
                "__name__": "__main__",
                "__builtins__": __builtins__
            }
            
            # TODO: 添加安全检查
            # - 禁止导入危险模块（os, subprocess 等）
            # - 限制内存使用
            # - 限制文件 I/O
            
            # 执行代码
            exec(code, global_namespace)
            
            # 捕获输出
            result["stdout"] = sys.stdout.getvalue()
            result["stderr"] = sys.stderr.getvalue()
            
            # 尝试解析 JSON 输出（如果有）
            stdout_text = result["stdout"].strip()
            if stdout_text:
                try:
                    # 假设输出的是 JSON
                    result["result"] = json.loads(stdout_text)
                except json.JSONDecodeError:
                    # 如果不是 JSON，保存原始文本
                    result["result"] = stdout_text
            
            result["success"] = True
            
        except Exception as e:
            # 捕获异常
            result["success"] = False
            result["error"] = {
                "type": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc()
            }
            result["stderr"] = sys.stderr.getvalue()
        
        finally:
            # 恢复标准输出
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        return result
    
    def validate_imports(self, code: str) -> tuple[bool, list[str]]:
        """
        检查代码中的导入语句
        
        Args:
            code: Python 代码
            
        Returns:
            (是否安全, 警告列表)
        """
        warnings = []
        
        # TODO: 实现导入安全检查
        # 危险模块黑名单
        # dangerous_modules = ['os', 'subprocess', 'sys', 'socket', 'requests']
        
        # 使用 ast 模块解析代码，提取 import 语句
        # import ast
        # tree = ast.parse(code)
        # for node in ast.walk(tree):
        #     if isinstance(node, ast.Import):
        #         for alias in node.names:
        #             if alias.name in dangerous_modules:
        #                 warnings.append(f"检测到危险模块导入: {alias.name}")
        
        return len(warnings) == 0, warnings
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        code = state.get("generated_code", "")
        
        # 执行代码
        execution_result = self.execute_code(code)
        
        # 更新状态
        state["execution_result"] = execution_result
        state["current_step"] = "execution_completed"
        
        # 根据执行结果设置下一步
        if execution_result["success"]:
            state["next_step"] = "validation"
        else:
            state["next_step"] = "debugging"
        
        return state


# 独立测试函数
def test_execution_tool():
    """测试执行工具"""
    tool = ExecutionTool()
    
    # 测试用例1：正常执行
    test_code_1 = '''
print("Hello, World!")
result = {"status": "ok", "value": 42}
import json
print(json.dumps(result))
'''
    
    print("测试用例1：正常执行")
    result1 = tool.execute_code(test_code_1)
    print(f"成功: {result1['success']}")
    print(f"输出: {result1['stdout']}")
    print()
    
    # 测试用例2：异常处理
    test_code_2 = '''
x = 1 / 0  # 会抛出 ZeroDivisionError
'''
    
    print("测试用例2：异常捕获")
    result2 = tool.execute_code(test_code_2)
    print(f"成功: {result2['success']}")
    print(f"错误: {result2['error']['type']}")
    print(f"消息: {result2['error']['message']}")
    print()


if __name__ == "__main__":
    test_execution_tool()
