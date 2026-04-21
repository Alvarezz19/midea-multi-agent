"""测试 config.py 中配置的 LLM 是否可用"""
import sys
import os
from pathlib import Path

# 禁用 LangSmith 追踪（在导入 langchain/config 之前）
os.environ["LANGCHAIN_TRACING_V2"] = "false"

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import config
from langchain_openai import ChatOpenAI
from colorama import init, Fore, Style

# 初始化 colorama
init(autoreset=True)


def test_llm_provider(provider_name: str, api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    """
    测试单个 LLM 提供商是否可用
    
    Args:
        provider_name: 提供商名称
        api_key: API 密钥
        base_url: API 基础 URL
        model: 模型名称
        
    Returns:
        (是否可用, 错误信息或成功响应)
    """
    if not api_key:
        return False, "未配置 API Key"
    
    try:
        # Kimi 模型只允许 temperature=1
        temperature = 1.0 if provider_name.lower() == "kimi" else 0.1
        
        # 创建 LLM 实例
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            timeout=30,
            max_retries=1
        )
        
        # 发送测试请求
        response = llm.invoke("你好，请回复'测试成功'")
        
        # 获取响应内容
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        return True, response_text[:100]  # 只返回前100个字符
        
    except Exception as e:
        error_msg = str(e)
        # 简化错误信息
        if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            return False, "认证失败 (API Key 无效)"
        elif "not found" in error_msg.lower() or "404" in error_msg:
            return False, "模型或端点不存在"
        elif "timeout" in error_msg.lower():
            return False, "连接超时"
        elif "connection" in error_msg.lower():
            return False, "连接失败"
        else:
            return False, f"错误: {error_msg[:100]}"


def print_result(provider_name: str, is_available: bool, message: str):
    """打印测试结果"""
    status = f"{Fore.GREEN}✓ 可用" if is_available else f"{Fore.RED}✗ 不可用"
    print(f"\n{provider_name:12} {status}")
    print(f"{'':12} {Fore.CYAN}{message}")


def main():
    """主测试函数"""
    print(f"\n{Fore.YELLOW}{'='*70}")
    print(f"{Fore.YELLOW}开始测试 LLM 可用性")
    print(f"{Fore.YELLOW}{'='*70}")
    
    # 测试配置列表
    test_configs = [
        {
            "name": "DeepSeek",
            "api_key": config.DEEPSEEK_API_KEY,
            "base_url": config.DEEPSEEK_BASE_URL,
            "model": config.DEEPSEEK_MODEL
        },
        {
            "name": "OpenAI",
            "api_key": config.OPENAI_API_KEY,
            "base_url": config.OPENAI_BASE_URL,
            "model": config.OPENAI_MODEL
        },
        {
            "name": "Qwen",
            "api_key": config.QWEN_API_KEY,
            "base_url": config.QWEN_BASE_URL,
            "model": config.QWEN_MODEL
        },
        {
            "name": "GLM",
            "api_key": config.GLM_API_KEY,
            "base_url": config.GLM_BASE_URL,
            "model": config.GLM_MODEL
        },
        {
            "name": "Kimi",
            "api_key": config.KIMI_API_KEY,
            "base_url": config.KIMI_BASE_URL,
            "model": config.KIMI_MODEL
        }
    ]
    
    # 统计结果
    available_count = 0
    total_count = len(test_configs)
    
    # 测试每个提供商
    for test_config in test_configs:
        is_available, message = test_llm_provider(
            test_config["name"],
            test_config["api_key"],
            test_config["base_url"],
            test_config["model"]
        )
        
        print_result(test_config["name"], is_available, message)
        
        if is_available:
            available_count += 1
    
    # 打印总结
    print(f"\n{Fore.YELLOW}{'='*70}")
    print(f"{Fore.YELLOW}测试完成: {available_count}/{total_count} 个 LLM 可用")
    print(f"{Fore.YELLOW}{'='*70}\n")
    
    # 显示当前配置的提供商
    current_provider = config.LLM_PROVIDER
    print(f"{Fore.CYAN}当前配置的 LLM 提供商: {Fore.WHITE}{current_provider}")
    
    # 检查当前配置的提供商是否可用
    for test_config in test_configs:
        if test_config["name"].lower() == current_provider.lower():
            is_available, _ = test_llm_provider(
                test_config["name"],
                test_config["api_key"],
                test_config["base_url"],
                test_config["model"]
            )
            if not is_available:
                print(f"{Fore.RED}警告: 当前配置的提供商 '{current_provider}' 不可用！")
            else:
                print(f"{Fore.GREEN}当前配置的提供商 '{current_provider}' 可正常使用")
            break
    
    print()


if __name__ == "__main__":
    main()
