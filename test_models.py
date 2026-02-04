"""
模型管理器测试脚本
用于测试不同的 LLM 和 Embedding 模型
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.model_manager import (
    LLMManager,
    EmbeddingManager,
    list_supported_llm_providers,
    list_supported_embedding_providers
)
import config


def show_current_config():
    """显示当前配置"""
    print("=" * 60)
    print("当前配置")
    print("=" * 60)
    print()
    print(f"📊 Embedding 提供商: {config.EMBEDDING_PROVIDER}")
    
    if config.EMBEDDING_PROVIDER == "bge":
        print(f"   模型: {config.BGE_MODEL_NAME}")
        print(f"   设备: {config.BGE_DEVICE}")
    elif config.EMBEDDING_PROVIDER == "siliconflow":
        print(f"   模型: {config.SILICONFLOW_EMBEDDING_MODEL}")
        print(f"   API: {config.SILICONFLOW_BASE_URL}")
        print(f"   API Key: {'已配置' if config.SILICONFLOW_API_KEY and config.SILICONFLOW_API_KEY != 'your_siliconflow_api_key_here' else '未配置'}")
    elif config.EMBEDDING_PROVIDER == "openai":
        print(f"   模型: {config.OPENAI_EMBEDDING_MODEL}")
        print(f"   API Key: {'已配置' if config.OPENAI_API_KEY and config.OPENAI_API_KEY != 'your_openai_api_key_here' else '未配置'}")
    
    print()
    print(f"🤖 LLM 提供商: {config.LLM_PROVIDER}")
    
    if config.LLM_PROVIDER == "deepseek":
        print(f"   模型: {config.DEEPSEEK_MODEL}")
        print(f"   API: {config.DEEPSEEK_BASE_URL}")
        print(f"   API Key: {'已配置' if config.DEEPSEEK_API_KEY and config.DEEPSEEK_API_KEY.startswith('sk-') else '未配置'}")
    elif config.LLM_PROVIDER == "openai":
        print(f"   模型: {config.OPENAI_MODEL}")
        print(f"   API Key: {'已配置' if config.OPENAI_API_KEY and config.OPENAI_API_KEY.startswith('sk-') else '未配置'}")
    elif config.LLM_PROVIDER == "qwen":
        print(f"   模型: {config.QWEN_MODEL}")
        print(f"   API Key: {'已配置' if config.QWEN_API_KEY and config.QWEN_API_KEY != 'your_qwen_api_key_here' else '未配置'}")
    elif config.LLM_PROVIDER == "glm":
        print(f"   模型: {config.GLM_MODEL}")
        print(f"   API Key: {'已配置' if config.GLM_API_KEY and config.GLM_API_KEY != 'your_glm_api_key_here' else '未配置'}")
    
    print()
    print(f"💾 向量数据库路径: {config.CHROMA_PERSIST_DIR}")
    print(f"🐛 调试模式: {config.DEBUG}")
    print()


def test_embedding_models():
    """测试当前配置的 Embedding 模型"""
    print("=" * 60)
    print("测试 Embedding 模型")
    print("=" * 60)
    
    providers = list_supported_embedding_providers()
    print(f"\n支持的 Embedding 提供商: {providers}\n")
    
    current_provider = config.EMBEDDING_PROVIDER
    print(f"测试当前配置的 Embedding ({current_provider})...\n")
    
    try:
        embedding = EmbeddingManager.get_embedding()
        
        # 测试嵌入
        test_texts = ["这是一个测试文本", "测试向量化功能"]
        print(f"   测试文本: {test_texts}")
        
        # ChromaDB 的 embedding function 调用方式
        if hasattr(embedding, '__call__'):
            print(f"   正在生成向量...")
            vectors = embedding(test_texts)
            print(f"   ✅ 成功生成向量")
            print(f"   向量维度: {len(vectors[0])}")
            print(f"   向量数量: {len(vectors)}")
        else:
            print(f"   ⚠️  Embedding 函数不可调用")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
    
    print()


def test_llm_models():
    """测试当前配置的 LLM 模型"""
    print("=" * 60)
    print("测试 LLM 模型")
    print("=" * 60)
    
    providers = list_supported_llm_providers()
    print(f"\n支持的 LLM 提供商: {providers}\n")
    
    current_provider = config.LLM_PROVIDER
    
    # 检查是否配置了有效的 API Key
    api_key_configured = False
    if current_provider == "deepseek":
        api_key_configured = config.DEEPSEEK_API_KEY and config.DEEPSEEK_API_KEY.startswith('sk-')
    elif current_provider == "openai":
        api_key_configured = config.OPENAI_API_KEY and config.OPENAI_API_KEY.startswith('sk-')
    elif current_provider == "qwen":
        api_key_configured = config.QWEN_API_KEY and config.QWEN_API_KEY != 'your_qwen_api_key_here'
    elif current_provider == "glm":
        api_key_configured = config.GLM_API_KEY and config.GLM_API_KEY != 'your_glm_api_key_here'
    
    if not api_key_configured:
        print(f"⚠️  {current_provider} API Key 未配置，跳过 LLM 测试")
        print(f"   请在 .env 文件中配置正确的 API Key\n")
        return
    
    print(f"测试当前配置的 LLM ({current_provider})...\n")
    try:
        llm = LLMManager.get_llm()
        print(f"   ✅ 成功初始化 {current_provider} LLM")
        
        # 简单测试
        print(f"   正在测试对话...")
        response = llm.invoke("你好，请用一句话介绍你自己")
        print(f"   测试响应: {response.content[:100]}...")
        print(f"   ✅ LLM 响应正常")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
    
    print()


def test_retrieval_agent():
    """测试检索智能体使用新的 Embedding"""
    print("=" * 60)
    print("测试检索智能体")
    print("=" * 60)
    
    from agents.retrieval_agent import RetrievalAgent
    
    print(f"\n当前配置的 Embedding 提供商: {config.EMBEDDING_PROVIDER}")
    print(f"当前配置的 LLM 提供商: {config.LLM_PROVIDER}\n")
    
    # 创建检索智能体（使用默认配置）
    print("创建检索智能体...")
    try:
        agent = RetrievalAgent()
        print(f"✅ 成功创建检索智能体")
        print(f"   知识库包含 {agent.collection.count()} 个模块\n")
        
        # 如果知识库为空，尝试加载
        if agent.collection.count() == 0:
            print("⚠️  知识库为空，需要先运行: python init_knowledge_base.py")
        else:
            # 测试检索
            print("测试检索功能...")
            result = agent.retrieve("比较两个温度值", top_k=3)
            
            if result['relevant_nodes']:
                print(f"\n找到 {len(result['relevant_nodes'])} 个相关模块:")
                for node in result['relevant_nodes']:
                    print(f"  - {node['name']} (分数: {node['similarity_score']:.3f})")
            else:
                print("未找到相关模块")
    
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
    
    print()


if __name__ == "__main__":
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "模型管理器测试工具" + " " * 15 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # 显示当前配置
    show_current_config()
    
    # 测试 Embedding 模型
    test_embedding_models()
    
    # 测试 LLM 模型
    test_llm_models()
    
    # 测试检索智能体
    # test_retrieval_agent()
    
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)
    print()
