"""项目配置文件"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ==================== LLM 配置 ====================
# 支持的 LLM 提供商
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")  # deepseek, openai, qwen, glm, kimi 等

# DeepSeek 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

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
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./outputs/chroma_db")
CHROMA_COLLECTION_ATOMIC_MODULES = os.getenv("CHROMA_COLLECTION_ATOMIC_MODULES", "kong_modules_v1")
CHROMA_COLLECTION_SUBFLOW_TEMPLATES = os.getenv("CHROMA_COLLECTION_SUBFLOW_TEMPLATES", "ahu_subflow_templates_v1")
CHROMA_COLLECTION_SYSTEM_PATTERNS = os.getenv("CHROMA_COLLECTION_SYSTEM_PATTERNS", "ahu_system_patterns_v1")
PHASE2_CHROMA_COLLECTION_OWNER = os.getenv("PHASE2_CHROMA_COLLECTION_OWNER", "phase2_ahu_assets")

# ==================== Phase 2 AHU Asset Output ====================
AHU_PATTERN_LIBRARY_DIR = os.getenv("AHU_PATTERN_LIBRARY_DIR", "AHU程序/pattern_library")


# ==================== 调试配置 ====================
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# ==================== 重试配置 ====================
MAX_RETRY_TIMES = int(os.getenv("MAX_RETRY_TIMES", "3"))

# ==================== 温度参数配置 ====================
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8192"))

# ==================== 分析智能体配置 ====================
ANALYSIS_LLM_PROVIDER = os.getenv("ANALYSIS_LLM_PROVIDER", "").strip()
ANALYSIS_LLM_MODEL = os.getenv("ANALYSIS_LLM_MODEL", "").strip()
ANALYSIS_LLM_TEMPERATURE = float(os.getenv("ANALYSIS_LLM_TEMPERATURE", "0.2"))
ANALYSIS_LLM_TIMEOUT_S = float(os.getenv("ANALYSIS_LLM_TIMEOUT_S", "30"))
ANALYSIS_MAX_AMBIGUITIES = int(os.getenv("ANALYSIS_MAX_AMBIGUITIES", "5"))
ANALYSIS_MAX_ASSUMPTIONS = int(os.getenv("ANALYSIS_MAX_ASSUMPTIONS", "5"))

# ==================== LLM 增强配置（默认关闭） ====================
# 总开关只记录增强层是否允许启用；具体节点仍由各自开关控制。
LLM_ENHANCEMENT_ENABLED = os.getenv("LLM_ENHANCEMENT_ENABLED", "false").lower() == "true"
LLM_ENHANCEMENT_PROVIDER = os.getenv("LLM_ENHANCEMENT_PROVIDER", "").strip()
LLM_ENHANCEMENT_MODEL = os.getenv("LLM_ENHANCEMENT_MODEL", "").strip()
LLM_ENHANCEMENT_TEMPERATURE = float(os.getenv("LLM_ENHANCEMENT_TEMPERATURE", "0.1"))
LLM_ENHANCEMENT_TIMEOUT_S = float(os.getenv("LLM_ENHANCEMENT_TIMEOUT_S", "20"))

# Analysis A0：工程需求编译器。默认关闭，确保旧 analysis 行为不变。
ANALYSIS_USE_ENGINEERING_COMPILER = os.getenv("ANALYSIS_USE_ENGINEERING_COMPILER", "false").lower() == "true"
ANALYSIS_ENGINEERING_LLM_PROVIDER = os.getenv("ANALYSIS_ENGINEERING_LLM_PROVIDER", "").strip()
ANALYSIS_ENGINEERING_LLM_MODEL = os.getenv("ANALYSIS_ENGINEERING_LLM_MODEL", "").strip()
ANALYSIS_ENGINEERING_LLM_TIMEOUT_S = float(os.getenv("ANALYSIS_ENGINEERING_LLM_TIMEOUT_S", "30"))

# ==================== 检索智能体 LLM 优化（默认关闭） ====================
# 说明：这些开关用于在检索阶段引入可选的 LLM 查询重写/轻量重排。
# 默认全部关闭，确保成本与延迟可控；LLM 不可用时实现必须自动兜底回退。
RETRIEVAL_USE_LLM_REWRITE = os.getenv("RETRIEVAL_USE_LLM_REWRITE", "false").lower() == "true"

# 可选：为检索优化指定独立的 provider/model；为空则复用全局 LLM_PROVIDER/默认模型
RETRIEVAL_LLM_PROVIDER = os.getenv("RETRIEVAL_LLM_PROVIDER", "").strip()
RETRIEVAL_LLM_MODEL = os.getenv("RETRIEVAL_LLM_MODEL", "").strip()

# 预算参数（与成本/延迟强相关）
RETRIEVAL_LLM_MAX_QUERIES = int(os.getenv("RETRIEVAL_LLM_MAX_QUERIES", "8"))
RETRIEVAL_LLM_TIMEOUT_S = float(os.getenv("RETRIEVAL_LLM_TIMEOUT_S", "8"))

# ==================== 检索 Cross-Encoder 重排（默认关闭） ====================
RETRIEVAL_USE_CROSS_ENCODER_RERANK = os.getenv("RETRIEVAL_USE_CROSS_ENCODER_RERANK", "false").lower() == "true"
RETRIEVAL_RERANKER_PROVIDER = os.getenv("RETRIEVAL_RERANKER_PROVIDER", "bge").strip()
RETRIEVAL_RERANKER_MODEL = os.getenv("RETRIEVAL_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3").strip()
RETRIEVAL_RERANK_TOP_N = int(os.getenv("RETRIEVAL_RERANK_TOP_N", "50"))
RETRIEVAL_RERANK_BATCH_SIZE = int(os.getenv("RETRIEVAL_RERANK_BATCH_SIZE", "16"))
RETRIEVAL_RERANK_TIMEOUT_S = float(os.getenv("RETRIEVAL_RERANK_TIMEOUT_S", "20"))

# ==================== 子系统规划 LLM 接口适配（默认关闭） ====================
SUBSYSTEM_USE_LLM_ADAPTER = os.getenv("SUBSYSTEM_USE_LLM_ADAPTER", "false").lower() == "true"
SUBSYSTEM_LLM_PROVIDER = os.getenv("SUBSYSTEM_LLM_PROVIDER", "").strip()
SUBSYSTEM_LLM_MODEL = os.getenv("SUBSYSTEM_LLM_MODEL", "").strip()
SUBSYSTEM_LLM_TIMEOUT_S = float(os.getenv("SUBSYSTEM_LLM_TIMEOUT_S", "30"))

# ==================== 架构规划 LLM Advisor（默认关闭） ====================
ARCHITECTURE_USE_LLM_ADVISOR = os.getenv("ARCHITECTURE_USE_LLM_ADVISOR", "false").lower() == "true"
ARCHITECTURE_LLM_PROVIDER = os.getenv("ARCHITECTURE_LLM_PROVIDER", "").strip()
ARCHITECTURE_LLM_MODEL = os.getenv("ARCHITECTURE_LLM_MODEL", "").strip()
ARCHITECTURE_LLM_TIMEOUT_S = float(os.getenv("ARCHITECTURE_LLM_TIMEOUT_S", "20"))
