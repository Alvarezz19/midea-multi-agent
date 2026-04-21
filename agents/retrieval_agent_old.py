"""
检索智能体 (Retrieval Agent)
职责：基于用户需求，从向量数据库中提取相关的领域知识
"""
from typing import Dict, List, Any, Optional
import json
import os
import glob
import re
import time
from pathlib import Path
import chromadb
import config
from langchain_core.prompts import ChatPromptTemplate
from utils.model_manager import EmbeddingManager, LLMManager
from utils.query_processor import QueryProcessor


class RetrievalAgent:
    """检索智能体"""
    
    def __init__(
        self,
        embedding_provider: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
    ):
        """
        初始化向量数据库和嵌入模型
        
        Args:
            embedding_provider: 嵌入模型提供商 (bge, openai, sentence-transformers, jina)
                               如果不指定，使用配置文件中的默认值
            llm_provider: 可选，用于检索优化（rewrite/rerank）的 LLM 提供商；为空则复用全局默认
            llm_model: 可选，用于检索优化（rewrite/rerank）的模型；为空则复用对应 provider 默认
        """
        # 初始化 ChromaDB 客户端
        self.client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        
        # 获取嵌入函数
        try:
            self.embedding_function = EmbeddingManager.get_embedding(embedding_provider)
        except Exception as e:
            if config.DEBUG:
                print(f"⚠️  使用指定的 embedding 模型失败: {e}")
                print("   使用默认 embedding 函数...")
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            self.embedding_function = DefaultEmbeddingFunction()
        
        # 获取或创建集合
        try:
            self.collection = self.client.get_collection(
                name="kong_modules_v1",
                embedding_function=self.embedding_function
            )
            if config.DEBUG:
                print(f"✅ 已加载现有知识库，包含 {self.collection.count()} 个模块")
        except Exception:
            # 集合不存在，创建新的
            self.collection = self.client.create_collection(
                name="kong_modules_v1",
                embedding_function=self.embedding_function,
                metadata={"description": "KONG CUBE 模块知识库"}
            )
            if config.DEBUG:
                print("📦 创建新的知识库集合")

        # LLM（用于可选的检索优化：rewrite/rerank）
        self._llm_provider = (
            (llm_provider or "").strip()
            or (config.RETRIEVAL_LLM_PROVIDER or "").strip()
            or None
        )
        self._llm_model = (
            (llm_model or "").strip()
            or (config.RETRIEVAL_LLM_MODEL or "").strip()
            or None
        )
        self._llm = None
        self._llm_init_attempted = False

        self._rewrite_prompt = self._create_rewrite_prompt()
        self._rewrite_cache: Dict[str, Dict[str, Any]] = {}

    # ==================== LLM 优化（可选） ====================

    def _ensure_llm(self):
        if self._llm_init_attempted:
            return self._llm

        self._llm_init_attempted = True
        try:
            kwargs: Dict[str, Any] = {}
            if self._llm_model:
                kwargs["model"] = self._llm_model
            # 统一设置超时（由底层 HTTP 客户端实现；不同 provider 可能忽略）
            kwargs["timeout"] = config.RETRIEVAL_LLM_TIMEOUT_S
            self._llm = LLMManager.get_llm(self._llm_provider, **kwargs)
        except Exception as e:
            self._llm = None
            if config.DEBUG:
                print(f"⚠️  检索优化 LLM 初始化失败，已回退: {e}")
        return self._llm

    def _create_rewrite_prompt(self) -> ChatPromptTemplate:
        system_prompt = """你是一个工业楼控/自动化模块检索专家。你的任务是分析用户需求，生成适合向量数据库检索的查询策略。

【知识库结构】
- 应用层模块：焓值、湿球温度、PID控制器等（复杂功能，直接可用）
- 基础组件：逻辑模块（比较、触发、通道选择）、运算模块（加减乘除）、变量模块（常量、变量）等

【分析策略】
1. 判断需求类型：
   - 简单需求：直接匹配单个模块（如"温度比较"→ 比较判断模块）
   - **复杂需求：需要多个基础模块组合**（如"温差计算公式"→ 减法+乘法+除法+常量）
   - 应用场景：可能存在现成的应用模块（如"空气焓值计算"→ 焓值模块）

2. 生成 queries 规则（**关键改进**）：
   第1层：应用场景查询（1条）
   - 保留完整的应用场景语义（如"主机负荷计算"）
   
   第2层：核心功能拆解（1-2条）
   - **显式提取计算逻辑**：如"温度差值计算"、"流量乘温差公式"
   - **识别条件判断**：如"根据输入0或1选择不同计算分支"
   
   第3层：基础组件关键词（2-3条）
   - **直接使用基础模块名称**：如"减法运算"、"乘法运算"、"除法运算"、"常量输入"
   - **逻辑控制组件**：如"通道选择"、"条件切换"
   
   数量：{max_queries} 条以内，优先级：应用 > 功能 > 基础组件

3. category_l1 推断：
   - 如果是现成应用场景 → "应用"
   - 如果需要条件判断 → "逻辑模块"
   - 如果主要是数学计算 → "运算模块"
   - 如果涉及数据采集/输出 → "变量模块"
   - **对于复杂组合需求，留空（不过滤类别）**

【约束】
- 输出必须是严格 JSON，不要输出任何额外解释
- queries 必须包含基础组件层查询（如"减法"、"乘法"）
- keywords 提取领域术语 + 基础运算名称

【允许的 category_l1 候选】
应用、逻辑模块、运算模块、变量模块、定时模块、累计模块、其他
（复杂组合需求建议留空）
"""

        user_template = """用户需求：{query}

请分析并输出：
{{
  "queries": ["应用场景查询1", "核心功能查询2", "基础组件查询3"],
  "category_l1": "推断的主类别",
  "keywords": ["领域术语1", "领域术语2", "..."],
  "notes": "需求类型（简单/复杂/应用场景）及推荐检索策略"
}}
"""

        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])

    @staticmethod
    def _extract_json_text(content: str) -> str:
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if json_match:
            return json_match.group(1).strip()

        # 尝试截取第一个 JSON 对象/数组
        obj_match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
        if obj_match:
            return obj_match.group(1).strip()

        return content.strip()

    def _llm_rewrite(self, query: str) -> Dict[str, Any]:
        cached = self._rewrite_cache.get(query)
        if cached is not None:
            return cached

        llm = self._ensure_llm()
        if llm is None:
            result = {"queries": [], "category_l1": "", "keywords": [], "notes": "llm_unavailable"}
            self._rewrite_cache[query] = result
            return result

        messages = self._rewrite_prompt.format_messages(
            query=query,
            max_queries=config.RETRIEVAL_LLM_MAX_QUERIES,
        )

        start = time.perf_counter()
        try:
            response = llm.invoke(messages)
            raw = self._extract_json_text(getattr(response, "content", "") or "")
            plan = json.loads(raw) if raw else {}
        except Exception as e:
            if config.DEBUG:
                elapsed = (time.perf_counter() - start) * 1000
                print(f"⚠️  LLM rewrite 失败({elapsed:.0f}ms)，已回退: {e}")
            plan = {}

        queries = plan.get("queries") if isinstance(plan, dict) else None
        if not isinstance(queries, list):
            queries = []

        result = {
            "queries": [q.strip() for q in queries if isinstance(q, str) and q.strip()][: config.RETRIEVAL_LLM_MAX_QUERIES],
            "category_l1": (plan.get("category_l1", "") or "").strip() if isinstance(plan, dict) else "",
            "keywords": plan.get("keywords", []) if isinstance(plan, dict) else [],
            "notes": plan.get("notes", "") if isinstance(plan, dict) else "",
        }

        self._rewrite_cache[query] = result
        return result
    
    # ==================== 相似度计算 ====================
    
    def _normalize_distance(self, distance: float) -> float:
        """
        将 L2 距离转换为相似度分数
        
        使用 1/(1+d) 公式，确保结果在 (0, 1] 范围内
        
        Args:
            distance: L2 欧氏距离
            
        Returns:
            相似度分数，范围 (0, 1]
        """
        return 1.0 / (1.0 + distance)
    
    def _serialize_module_to_text(self, module_json: Dict[str, Any]) -> str:
        """
        将模块 JSON 转换为富含语义的自然语言文本块
        
        Args:
            module_json: 模块的 JSON Schema
            
        Returns:
            语义文本块
        """
        lines = []
        
        # 1. 核心身份（增加权重）
        module_type = module_json.get('module_type', '')
        name = module_json.get('name', '')
        category = module_json.get('category', '')
        
        lines.append(f"# 模块名称: {name}")
        lines.append(f"模块类型: {module_type}")
        lines.append(f"模块类别: {category}")
        lines.append("")
        
        # 2. 核心描述（这是检索的关键）
        description = module_json.get('description', '')
        if description:
            lines.append(f"## 功能描述")
            lines.append(description)
            lines.append("")
        
        # 3. 关键词扩展
        keywords = module_json.get('keywords', [])
        if keywords:
            lines.append(f"## 关键词")
            lines.append(", ".join(keywords))
            lines.append("")
        
        # 4. 使用场景（非常重要，匹配用户意图）
        usage_guides = module_json.get('usage_guides', [])
        if usage_guides:
            lines.append("## 适用场景")
            for guide in usage_guides:
                lines.append(f"- {guide}")
            lines.append("")
        
        # 5. 参数语义（只提取参数名和描述）
        params_schema = module_json.get('parameters_schema', {})
        if params_schema:
            lines.append("## 参数功能")
            for key, info in params_schema.items():
                # 跳过纯技术参数
                if key not in ['x', 'y', 'wires', 'id', 'z']:
                    param_desc = info.get('description', '')
                    param_type = info.get('type', '')
                    param_enum = info.get('enum', [])
                    
                    line = f"- **{key}** ({param_type}): {param_desc}"
                    if param_enum:
                        line += f" [可选值: {', '.join(map(str, param_enum))}]"
                    lines.append(line)
            lines.append("")
        
        # 6. 端口语义（利用 ports_definition）
        ports_def = module_json.get('ports_definition', {})
        if ports_def:
            lines.append("## 输入输出端口")
            
            inputs = ports_def.get('inputs', [])
            if inputs:
                lines.append("### 输入端口")
                for inp in inputs:
                    label = inp.get('label', '')
                    desc = inp.get('description', '')
                    port_type = inp.get('type', '')
                    condition = inp.get('condition', 'always')
                    
                    line = f"- **{label}** ({port_type}): {desc}"
                    if condition != 'always':
                        line += f" [条件: {condition}]"
                    lines.append(line)
            
            outputs = ports_def.get('outputs', [])
            if outputs:
                lines.append("### 输出端口")
                for out in outputs:
                    label = out.get('label', '')
                    desc = out.get('description', '')
                    port_type = out.get('type', '')
                    condition = out.get('condition', 'always')
                    
                    line = f"- **{label}** ({port_type}): {desc}"
                    if condition != 'always':
                        line += f" [条件: {condition}]"
                    lines.append(line)
            lines.append("")
        
        return "\n".join(lines)
    
    def _extract_metadata(self, module_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取模块的元数据用于过滤和检索
        
        Args:
            module_json: 模块的 JSON Schema
            
        Returns:
            元数据字典
        """
        category = module_json.get('category', '')
        category_parts = category.split('/')
        
        # 检查是否有动态端口
        ports_def = module_json.get('ports_definition', {})
        has_dynamic_ports = False
        for inp in ports_def.get('inputs', []):
            if inp.get('condition', 'always') != 'always':
                has_dynamic_ports = True
                break
        
        metadata = {
            "module_id": module_json.get('id', ''),
            "module_type": module_json.get('module_type', ''),
            "category": category,
            "category_l1": category_parts[0] if len(category_parts) > 0 else '',
            "category_l2": category_parts[1] if len(category_parts) > 1 else '',
            "has_dynamic_ports": has_dynamic_ports,
            "keywords": ','.join(module_json.get('keywords', [])),
            "json_schema": json.dumps(module_json, ensure_ascii=False)
        }
        
        return metadata
    
    def retrieve(self, query: str, top_k: int = 10, 
                 category_filter: Optional[str] = None,
                 similarity_threshold: float = 0.3,
                 use_query_enhancement: bool = True,
                 use_llm_rewrite: Optional[bool] = None,
                 ) -> Dict[str, Any]:
        """
        检索相关知识
        
        Args:
            query: 用户查询/需求
            top_k: 返回的最相关文档数量
            category_filter: 可选的类别过滤（如 "逻辑模块"）
            similarity_threshold: 相似度阈值，低于此值的结果将被过滤
            use_query_enhancement: 是否使用查询增强（针对复杂查询）
            
        Returns:
            包含上下文信息的字典
        """
        if config.DEBUG:
            print(f"\n🔍 开始检索: {query}")
            print(f"   Top-K: {top_k}, 类别过滤: {category_filter or '无'}")

        rewrite_enabled = config.RETRIEVAL_USE_LLM_REWRITE if use_llm_rewrite is None else bool(use_llm_rewrite)
        rewrite_plan: Optional[Dict[str, Any]] = None
        rewrite_used = False
        
        # 查询增强（规则）
        enhanced: Optional[Dict[str, Any]] = QueryProcessor.enhance_query(query) if use_query_enhancement else None

        # LLM 查询重写（默认关闭；仅在复杂查询时触发）
        if rewrite_enabled and QueryProcessor.should_use_multi_query(query):
            rewrite_plan = self._llm_rewrite(query)
            llm_queries = rewrite_plan.get("queries", []) if isinstance(rewrite_plan, dict) else []
            llm_category_l1 = (rewrite_plan.get("category_l1", "") or "").strip() if isinstance(rewrite_plan, dict) else ""

            if llm_category_l1 and not category_filter:
                # 为避免误过滤，仅当看起来像合法的一级类目时启用
                allowed_prefixes = {
                    "逻辑模块",
                    "运算模块",
                    "变量模块",
                    "定时模块",
                    "累计模块",
                    "应用",
                    "基础组件",
                    "高级组件",
                    "备注组件",
                    "其他",
                }
                if llm_category_l1 in allowed_prefixes:
                    category_filter = llm_category_l1

            if llm_queries:
                rewrite_used = True
                if enhanced is None:
                    enhanced = {
                        "original_query": query,
                        "query_variants": llm_queries,
                        "detected_operations": [],
                        "keyword_patterns": {},
                        "has_variables": False,
                        "has_constants": False,
                        "intent": "general_query",
                    }
                else:
                    enhanced = dict(enhanced)
                    enhanced["query_variants"] = llm_queries
            
        if enhanced is not None and config.DEBUG and len(enhanced.get('detected_operations', [])) > 0:
            print(f"   🔧 检测到运算: {', '.join(enhanced['detected_operations'])}")

        # 存在多个查询变体时直接走多查询策略（变体来源可能来自规则或 LLM）
        if enhanced is not None and len(enhanced.get("query_variants", [])) > 1:
            context = self._multi_query_retrieve(
                enhanced, top_k, category_filter, similarity_threshold
            )
        else:
            # 标准单查询检索（向量检索）
            context = self._single_query_retrieve(
                query, top_k, category_filter, similarity_threshold
            )

        # 增强元数据（可观测）
        meta = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
        meta = dict(meta)
        meta.update({
            "rewrite_used": rewrite_used,
        })
        if rewrite_used and isinstance(rewrite_plan, dict):
            meta["llm_queries"] = rewrite_plan.get("queries", [])
            meta["llm_category_l1"] = rewrite_plan.get("category_l1", "")
        context["metadata"] = meta

        return context
    
    def _single_query_retrieve(self, query: str, top_k: int,
                               category_filter: Optional[str],
                               similarity_threshold: float) -> Dict[str, Any]:
        """
        单查询检索（原始方法）
        
        Args:
            query: 查询文本
            top_k: 返回数量
            category_filter: 类别过滤
            similarity_threshold: 相似度阈值
            
        Returns:
            检索结果
        """
        
        # 构建查询条件
        where_clause = {}
        if category_filter:
            where_clause["category_l1"] = category_filter

        documents: List[str] = []
        
        try:
            # 执行向量检索
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_clause if where_clause else None
            )
            
            # 解析检索结果
            relevant_nodes = []
            similar_cases = []
            
            if results and results['documents'] and len(results['documents'][0]) > 0:
                documents = results['documents'][0]
                metadatas = results['metadatas'][0]
                distances = results['distances'][0] if 'distances' in results else [0] * len(documents)
                
                for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
                    # 计算相似度分数（使用归一化公式，确保结果在 (0, 1] 范围）
                    similarity_score = self._normalize_distance(distance)
                    
                    # 阈值过滤
                    if similarity_score < similarity_threshold:
                        if config.DEBUG:
                            print(f"   ⚠️  过滤低分结果: {metadata.get('module_type')} (分数: {similarity_score:.3f})")
                        continue
                    
                    # 解析 JSON Schema
                    try:
                        module_schema = json.loads(metadata.get('json_schema', '{}'))
                        
                        # 提取节点信息
                        node_info = {
                            "module_type": metadata.get('module_type'),
                            "name": module_schema.get('name'),
                            "description": module_schema.get('description'),
                            "category": metadata.get('category'),
                            "parameters_schema": module_schema.get('parameters_schema', {}),
                            "ports_definition": module_schema.get('ports_definition', {}),
                            "template_json": module_schema.get('template_json', {}),
                            "keywords": module_schema.get('keywords', []),
                            "usage_guides": module_schema.get('usage_guides', []),
                            "similarity_score": similarity_score,
                            "rank": i + 1
                        }
                        
                        relevant_nodes.append(node_info)
                        
                        # 生成示例代码（伪代码）
                        example_code = self._generate_example_code(module_schema)
                        similar_cases.append({
                            "module_type": metadata.get('module_type'),
                            "example_code": example_code
                        })
                        
                        if config.DEBUG:
                            print(f"   ✅ 匹配 #{i+1}: {metadata.get('module_type')} "
                                  f"({node_info['name']}) - 分数: {similarity_score:.3f}")
                    
                    except json.JSONDecodeError as e:
                        if config.DEBUG:
                            print(f"   ❌ JSON 解析错误: {e}")
                        continue
            
            # 构建上下文
            context = {
                "query": query,
                "relevant_nodes": relevant_nodes,
                "similar_cases": similar_cases,
                "metadata": {
                    "retrieved_count": len(relevant_nodes),
                    "total_candidates": len(documents),
                    "category_filter": category_filter,
                    "avg_confidence_score": sum(n['similarity_score'] for n in relevant_nodes) / len(relevant_nodes) if relevant_nodes else 0
                }
            }
            
            if config.DEBUG:
                print(f"   📊 检索完成: 找到 {len(relevant_nodes)} 个相关模块\n")
            
            return context
        
        except Exception as e:
            if config.DEBUG:
                print(f"   ❌ 检索失败: {e}")
            
            return {
                "query": query,
                "relevant_nodes": [],
                "similar_cases": [],
                "metadata": {
                    "retrieved_count": 0,
                    "error": str(e)
                }
            }
    
    def _multi_query_retrieve(self, enhanced: Dict[str, Any], top_k: int,
                             category_filter: Optional[str],
                             similarity_threshold: float) -> Dict[str, Any]:
        """
        多查询检索策略（用于复杂查询）
        
        利用 ChromaDB 的批量查询能力，将所有查询变体合并为一次
        collection.query() 调用，避免逐条串行检索带来的 I/O 开销。
        
        Args:
            enhanced: 增强后的查询信息
            top_k: 返回数量
            category_filter: 类别过滤
            similarity_threshold: 相似度阈值
            
        Returns:
            合并后的检索结果
        """
        query_variants = enhanced['query_variants']
        
        if config.DEBUG:
            print(f"   🎯 使用批量多查询策略，变体数量: {len(query_variants)}")
            for v in query_variants:
                print(f"   📝 查询变体: {v}")
        
        # 构建查询条件
        where_clause = {}
        if category_filter:
            where_clause["category_l1"] = category_filter
        
        per_variant_k = min(top_k, 5)  # 每个变体返回较少结果
        
        all_results = {}  # 使用字典去重，key 为 module_type
        
        try:
            # ====== 核心改动：单次批量向量检索 ======
            # ChromaDB query() 支持 query_texts 传入多条文本，
            # 返回结果按 query_texts 顺序索引：
            #   results['documents'][i]  → 第 i 条查询的文档列表
            #   results['metadatas'][i]  → 第 i 条查询的元数据列表
            #   results['distances'][i]  → 第 i 条查询的距离列表
            results = self.collection.query(
                query_texts=query_variants,
                n_results=per_variant_k,
                where=where_clause if where_clause else None
            )
            
            # 遍历每条查询变体的结果
            for variant_idx, variant in enumerate(query_variants):
                if (not results or not results['documents']
                        or variant_idx >= len(results['documents'])):
                    continue
                
                documents = results['documents'][variant_idx]
                metadatas = results['metadatas'][variant_idx]
                distances = (results['distances'][variant_idx]
                             if 'distances' in results and variant_idx < len(results['distances'])
                             else [0] * len(documents))
                
                for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
                    similarity_score = self._normalize_distance(distance)
                    
                    # 阈值过滤
                    if similarity_score < similarity_threshold:
                        if config.DEBUG:
                            print(f"   ⚠️  过滤低分结果: {metadata.get('module_type')} "
                                  f"(分数: {similarity_score:.3f}, 来源: 变体#{variant_idx+1})")
                        continue
                    
                    module_type = metadata.get('module_type')
                    
                    # 去重：保留最高相似度分数
                    if (module_type in all_results
                            and similarity_score <= all_results[module_type]['similarity_score']):
                        continue
                    
                    # 解析 JSON Schema
                    try:
                        module_schema = json.loads(metadata.get('json_schema', '{}'))
                    except json.JSONDecodeError as e:
                        if config.DEBUG:
                            print(f"   ❌ JSON 解析错误: {e}")
                        continue
                    
                    node_info = {
                        "module_type": module_type,
                        "name": module_schema.get('name'),
                        "description": module_schema.get('description'),
                        "category": metadata.get('category'),
                        "parameters_schema": module_schema.get('parameters_schema', {}),
                        "ports_definition": module_schema.get('ports_definition', {}),
                        "template_json": module_schema.get('template_json', {}),
                        "keywords": module_schema.get('keywords', []),
                        "usage_guides": module_schema.get('usage_guides', []),
                        "similarity_score": similarity_score,
                        "rank": 0,  # 稍后重新计算
                        "matched_query": variant,
                    }
                    
                    all_results[module_type] = node_info
                    
                    if config.DEBUG:
                        print(f"   ✅ 匹配: {module_type} ({node_info['name']}) "
                              f"- 分数: {similarity_score:.3f} (变体#{variant_idx+1})")
        
        except Exception as e:
            if config.DEBUG:
                print(f"   ❌ 批量检索失败: {e}")
            return {
                "query": enhanced['original_query'],
                "relevant_nodes": [],
                "similar_cases": [],
                "metadata": {
                    "retrieved_count": 0,
                    "error": str(e)
                }
            }
        
        # 按相似度排序
        sorted_nodes = sorted(
            all_results.values(),
            key=lambda x: x['similarity_score'],
            reverse=True
        )[:top_k]
        
        # 重新计算排名
        for i, node in enumerate(sorted_nodes):
            node['rank'] = i + 1
        
        # 生成示例代码
        similar_cases = []
        for node in sorted_nodes:
            example_code = f"# {node['name']}\n# 类型: {node['module_type']}"
            similar_cases.append({
                "module_type": node['module_type'],
                "example_code": example_code
            })
        
        if config.DEBUG:
            print(f"   🎯 批量多查询合并完成: 找到 {len(sorted_nodes)} 个相关模块")
        
        return {
            "query": enhanced['original_query'],
            "relevant_nodes": sorted_nodes,
            "similar_cases": similar_cases,
            "metadata": {
                "retrieved_count": len(sorted_nodes),
                "query_variants_used": len(query_variants),
                "detected_operations": enhanced['detected_operations'],
                "intent": enhanced['intent'],
                "avg_confidence_score": sum(n['similarity_score'] for n in sorted_nodes) / len(sorted_nodes) if sorted_nodes else 0
            }
        }
    
    def _generate_example_code(self, module_schema: Dict[str, Any]) -> str:
        """
        生成模块的示例代码（伪代码）
        
        Args:
            module_schema: 模块的 JSON Schema
            
        Returns:
            示例代码字符串
        """
        module_type = module_schema.get('module_type', '')
        name = module_schema.get('name', '')
        params = module_schema.get('parameters_schema', {})
        
        lines = [
            f"# 示例：使用 {name} 模块",
            f"# 模块类型: {module_type}",
            ""
        ]
        
        # 生成参数示例
        param_examples = []
        for key, info in params.items():
            if key not in ['x', 'y', 'wires', 'id', 'z']:
                default_val = info.get('default', '')
                if isinstance(default_val, str):
                    param_examples.append(f"    '{key}': '{default_val}'")
                else:
                    param_examples.append(f"    '{key}': {default_val}")
        
        lines.append("node = {")
        lines.append(f"    'type': '{module_type}',")
        lines.append(f"    'name': '自定义名称',")
        if param_examples:
            lines.extend(param_examples)
        lines.append("}")
        
        return "\n".join(lines)
    
    def load_knowledge_base(self, schemas_dir: str = "./schemas"):
        """
        加载知识库
        
        Args:
            schemas_dir: JSON Schema 文件所在目录
        """
        if config.DEBUG:
            print(f"\n📚 开始加载知识库: {schemas_dir}")
        
        # 查找所有 JSON 文件（排除扩展描述文件）
        json_files = []
        for root, dirs, files in os.walk(schemas_dir):
            for file in files:
                if file.endswith('.json') and file != '扩展描述文件.json':
                    json_files.append(os.path.join(root, file))
        
        if config.DEBUG:
            print(f"   找到 {len(json_files)} 个模块定义文件")
        
        # 批量加载
        documents = []
        metadatas = []
        ids = []
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    module_json = json.load(f)
                
                # 生成语义文本块
                doc_text = self._serialize_module_to_text(module_json)
                
                # 提取元数据
                metadata = self._extract_metadata(module_json)
                
                # 生成唯一 ID
                module_type = module_json.get('module_type', '')
                category = module_json.get('category', '').replace('/', '_')
                doc_id = f"{category}_{module_type}"
                
                documents.append(doc_text)
                metadatas.append(metadata)
                ids.append(doc_id)
                
                if config.DEBUG:
                    print(f"   ✅ 加载: {module_json.get('name')} ({module_type})")
            
            except Exception as e:
                if config.DEBUG:
                    print(f"   ❌ 加载失败 {json_file}: {e}")
        
        # 批量插入向量数据库
        if documents:
            try:
                self.collection.upsert(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                
                if config.DEBUG:
                    print(f"\n✅ 知识库加载完成！总计 {len(documents)} 个模块")
                    print(f"   向量数据库当前包含 {self.collection.count()} 条记录")
            
            except Exception as e:
                if config.DEBUG:
                    print(f"\n❌ 向量数据库插入失败: {e}\n")
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 节点调用接口
        
        Args:
            state: 当前工作流状态
            
        Returns:
            更新后的状态
        """
        user_query = state.get("user_query", "")
        
        # 执行检索
        context = self.retrieve(user_query)
        
        # 更新状态
        state["retrieval_context"] = context
        state["current_step"] = "retrieval_completed"
        
        return state
