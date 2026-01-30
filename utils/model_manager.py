"""
模型管理器
统一管理多种 LLM 和 Embedding 模型
"""
from typing import Optional, Any
import config


class LLMManager:
    """大语言模型管理器"""
    
    @staticmethod
    def get_llm(provider: Optional[str] = None, **kwargs):
        """
        获取 LLM 实例
        
        Args:
            provider: LLM 提供商 (deepseek, openai, qwen, glm)
            **kwargs: 额外参数
            
        Returns:
            LLM 实例
        """
        provider = provider or config.LLM_PROVIDER
        
        if config.DEBUG:
            print(f"🤖 初始化 LLM: {provider}")
        
        if provider == "deepseek":
            return LLMManager._get_deepseek(**kwargs)
        elif provider == "openai":
            return LLMManager._get_openai(**kwargs)
        elif provider == "qwen":
            return LLMManager._get_qwen(**kwargs)
        elif provider == "glm":
            return LLMManager._get_glm(**kwargs)
        else:
            raise ValueError(f"不支持的 LLM 提供商: {provider}")
    
    @staticmethod
    def _get_deepseek(**kwargs):
        """获取 DeepSeek LLM"""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model=kwargs.get('model', config.DEEPSEEK_MODEL),
            temperature=kwargs.get('temperature', config.LLM_TEMPERATURE),
            max_tokens=kwargs.get('max_tokens', config.LLM_MAX_TOKENS)
        )
    
    @staticmethod
    def _get_openai(**kwargs):
        """获取 OpenAI LLM"""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            model=kwargs.get('model', config.OPENAI_MODEL),
            temperature=kwargs.get('temperature', config.LLM_TEMPERATURE),
            max_tokens=kwargs.get('max_tokens', config.LLM_MAX_TOKENS)
        )
    
    @staticmethod
    def _get_qwen(**kwargs):
        """获取通义千问 LLM"""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            api_key=config.QWEN_API_KEY,
            base_url=config.QWEN_BASE_URL,
            model=kwargs.get('model', config.QWEN_MODEL),
            temperature=kwargs.get('temperature', config.LLM_TEMPERATURE),
            max_tokens=kwargs.get('max_tokens', config.LLM_MAX_TOKENS)
        )
    
    @staticmethod
    def _get_glm(**kwargs):
        """获取智谱 GLM LLM"""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            api_key=config.GLM_API_KEY,
            base_url=config.GLM_BASE_URL,
            model=kwargs.get('model', config.GLM_MODEL),
            temperature=kwargs.get('temperature', config.LLM_TEMPERATURE),
            max_tokens=kwargs.get('max_tokens', config.LLM_MAX_TOKENS)
        )


class EmbeddingManager:
    """嵌入模型管理器"""
    
    @staticmethod
    def get_embedding(provider: Optional[str] = None, **kwargs):
        """
        获取 Embedding 实例
        
        Args:
            provider: Embedding 提供商 (bge, openai, sentence-transformers, jina, siliconflow)
            **kwargs: 额外参数
            
        Returns:
            Embedding 实例（适配 ChromaDB）
        """
        provider = provider or config.EMBEDDING_PROVIDER
        
        if config.DEBUG:
            print(f"📊 初始化 Embedding: {provider}")
        
        if provider == "bge":
            return EmbeddingManager._get_bge(**kwargs)
        elif provider == "siliconflow":
            return EmbeddingManager._get_siliconflow(**kwargs)
        elif provider == "openai":
            return EmbeddingManager._get_openai_embedding(**kwargs)
        elif provider == "sentence-transformers":
            return EmbeddingManager._get_sentence_transformers(**kwargs)
        elif provider == "jina":
            return EmbeddingManager._get_jina(**kwargs)
        else:
            raise ValueError(f"不支持的 Embedding 提供商: {provider}")
    
    @staticmethod
    def _get_bge(**kwargs):
        """
        获取 BGE Embedding（本地模型）
        使用 HuggingFace Sentence Transformers
        """
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        
        model_name = kwargs.get('model_name', config.BGE_MODEL_NAME)
        device = kwargs.get('device', config.BGE_DEVICE)
        
        if config.DEBUG:
            print(f"   模型: {model_name}")
            print(f"   设备: {device}")
        
        return SentenceTransformerEmbeddingFunction(
            model_name=model_name,
            device=device
        )
    
    @staticmethod
    def _get_siliconflow(**kwargs):
        """
        获取硅基流动 BGE-M3 Embedding（API）
        使用 OpenAI 兼容接口
        """
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        
        if not config.SILICONFLOW_API_KEY:
            raise ValueError("SILICONFLOW_API_KEY 未配置")
        
        model_name = kwargs.get('model_name', config.SILICONFLOW_EMBEDDING_MODEL)
        
        if config.DEBUG:
            print(f"   模型: {model_name}")
            print(f"   API: {config.SILICONFLOW_BASE_URL}")
        
        return OpenAIEmbeddingFunction(
            api_key=config.SILICONFLOW_API_KEY,
            api_base=config.SILICONFLOW_BASE_URL,
            model_name=model_name
        )
    
    @staticmethod
    def _get_openai_embedding(**kwargs):
        """获取 OpenAI Embedding"""
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未配置")
        
        return OpenAIEmbeddingFunction(
            api_key=config.OPENAI_API_KEY,
            api_base=config.OPENAI_BASE_URL,
            model_name=kwargs.get('model_name', config.OPENAI_EMBEDDING_MODEL)
        )
    
    @staticmethod
    def _get_sentence_transformers(**kwargs):
        """获取 Sentence Transformers Embedding"""
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        
        model_name = kwargs.get('model_name', config.SENTENCE_TRANSFORMER_MODEL)
        
        return SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )
    
    @staticmethod
    def _get_jina(**kwargs):
        """
        获取 Jina Embedding
        注意：需要自定义实现 Jina API 调用
        """
        # TODO: 实现 Jina Embedding 适配器
        # ChromaDB 没有内置的 Jina embedding function
        # 需要自定义一个 Emsiliconflow", "beddingFunction 类
        raise NotImplementedError("Jina Embedding 需要自定义实现")


# ==================== 便捷函数 ====================

def get_default_llm(**kwargs):
    """获取默认配置的 LLM"""
    return LLMManager.get_llm(**kwargs)


def get_default_embedding(**kwargs):
    """获取默认配置的 Embedding"""
    return EmbeddingManager.get_embedding(**kwargs)


def list_supported_llm_providers():
    """列出支持的 LLM 提供商"""
    return ["deepseek", "openai", "qwen", "glm"]


def list_supported_embedding_providers():
    """列出支持的 Embedding 提供商"""
    return ["bge", "openai", "sentence-transformers", "jina"]
