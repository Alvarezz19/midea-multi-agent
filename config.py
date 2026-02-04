"""项目配置文件"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== LLM 配置 ====================
# 支持的 LLM 提供商
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")  # deepseek, openai, qwen, glm, kimi 等

# DeepSeek 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# OpenAI 配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")

# 通义千问配置
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-max")

# 智谱 GLM 配置
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4")

# Kimi 配置（Moonshot）
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")

# ==================== Embedding 配置 ====================
# 支持的 Embedding 提供商
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "bge")  # bge, openai, sentence-transformers, jina, siliconflow

# BGE 配置（本地模型）
BGE_MODEL_NAME = os.getenv("BGE_MODEL_NAME", "BAAI/bge-m3")
BGE_DEVICE = os.getenv("BGE_DEVICE", "cpu")  # cpu 或 cuda

# 硅基流动配置（BGE-M3 API）
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_EMBEDDING_MODEL = os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")

# OpenAI Embedding 配置
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")

# Sentence Transformers 配置
SENTENCE_TRANSFORMER_MODEL = os.getenv("SENTENCE_TRANSFORMER_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Jina Embedding 配置
JINA_API_KEY = os.getenv("JINA_API_KEY", "")
JINA_MODEL = os.getenv("JINA_MODEL", "jina-embeddings-v2-base-zh")

# ==================== 向量数据库配置 ====================
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

# ==================== 调试配置 ====================
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# ==================== 重试配置 ====================
MAX_RETRY_TIMES = int(os.getenv("MAX_RETRY_TIMES", "3"))

# ==================== 温度参数配置 ====================
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8192"))
