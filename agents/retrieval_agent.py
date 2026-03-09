"""
检索智能体 (Retrieval Agent) — v2
职责：基于用户需求，通过 LLM 进行意图推断和查询生成，
      然后从向量数据库中检索相关的领域知识。

变更说明（相对 retrieval_agent_old.py）：
  - 移除 QueryProcessor 规则查询增强
  - LLM 意图分析与查询生成成为主流程
  - LLM 不可用时，兜底使用原始查询做单次检索
  - 输出结构（retrieval_context）与旧版完全一致
"""
from typing import Dict, List, Any, Optional
import json
import os
import re
import time
import chromadb
import config
from langchain_core.prompts import ChatPromptTemplate
from utils.model_manager import EmbeddingManager, LLMManager


class RetrievalAgent:
    """检索智能体（LLM 驱动）"""

    def __init__(
        self,
        embedding_provider: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
    ):
        """
        初始化向量数据库、嵌入模型和 LLM

        Args:
            embedding_provider: 嵌入模型提供商 (bge, openai, sentence-transformers, jina)
                               如果不指定，使用配置文件中的默认值
            llm_provider: LLM 提供商；为空则复用全局默认
            llm_model: LLM 模型名；为空则复用对应 provider 默认
        """
        # ==================== ChromaDB 初始化 ====================
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
            self.collection = self.client.create_collection(
                name="kong_modules_v1",
                embedding_function=self.embedding_function,
                metadata={"description": "KONG CUBE 模块知识库"}
            )
            if config.DEBUG:
                print("📦 创建新的知识库集合")

        # ==================== LLM 初始化（懒加载） ====================
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

        # Prompt 与缓存
        self._analyze_prompt = self._create_analyze_prompt()
        self._analyze_cache: Dict[str, Dict[str, Any]] = {}

    # ==================== LLM 管理 ====================

    def _ensure_llm(self):
        """懒加载 LLM，仅尝试初始化一次"""
        if self._llm_init_attempted:
            return self._llm

        self._llm_init_attempted = True
        try:
            kwargs: Dict[str, Any] = {}
            if self._llm_model:
                kwargs["model"] = self._llm_model
            kwargs["timeout"] = config.RETRIEVAL_LLM_TIMEOUT_S
            self._llm = LLMManager.get_llm(self._llm_provider, **kwargs)
            if config.DEBUG:
                print(f"✅ 检索智能体 LLM 初始化成功")
        except Exception as e:
            self._llm = None
            if config.DEBUG:
                print(f"⚠️  检索智能体 LLM 初始化失败，将使用兜底策略: {e}")
        return self._llm

    # ==================== LLM 意图分析 Prompt ====================

    def _create_analyze_prompt(self) -> ChatPromptTemplate:
        """创建 LLM 意图分析与查询生成的 Prompt"""
        system_prompt = """你是一个工业楼控/自动化模块检索专家。你的任务是分析用户需求，推断意图，并生成适合向量数据库检索的多个查询变体。

【知识库结构】
知识库中包含以下类型的模块定义（JSON Schema）：
- 应用层模块：焓值、含湿量、露点温度、湿球温度、PID控制器、自适应PID、通用电加热加减载逻辑等（复杂功能，直接可用）
- 逻辑模块：比较判断、边沿触发、触发开关、回差控制、逻辑运算、数据锁存、通道选择、线性变换、限值、RS触发器、SR触发器
- 运算模块：加、减、乘、除、绝对值、幂运算、对数、模、取位、取整、三角函数、统计运算、位运算、位组合、移位
- 变量模块：变量、常量、物理输入、物理输出、节点监测、系统时间、引用、BACIP_IO、Modbus_IO、MQTT订阅、MQTT发布
- 定时模块：定时更新、定时脉冲、延时关、延时开
- 累计模块：计数器、累加器、运行时间
- 其他：备注模块

【你需要输出的内容】

1. **queries**（最重要）：生成 {max_queries} 条以内的检索查询变体，用于向量数据库检索。
   生成策略（按层优先级）：
   - 第1层：应用场景查询（1条）— 保留完整的需求语义，如"夏季主机负荷计算"
   - 第2层：核心功能拆解（1-2条）— 提取计算逻辑，如"温度差值计算"、"流量乘温差公式"
   - 第3层：基础组件关键词（2-4条）— 直接使用基础模块名称，如"减法运算"、"乘法运算"、"常量输入"、"通道选择"
   
   **要求**：
   - 必须包含基础组件层查询（如具体的运算模块名称）
   - 对于公式需求，拆解出每个需要的基础运算
   - 对于条件判断需求，包含逻辑控制组件名称

2. **category_l1**：推断的一级分类（用于缩小检索范围）
   - 如果是现成应用场景 → "应用"
   - 如果需要条件判断 → "逻辑模块"
   - 如果主要是数学计算 → "运算模块"
   - 如果涉及数据采集/输出 → "变量模块"
   - **对于复杂组合需求（需要多类模块），留空字符串**

3. **intent**：意图分类，必须是以下枚举值之一：
   - "mathematical_computation"：包含数学公式或运算
   - "comparison"：包含比较/判断逻辑
   - "logic_operation"：包含逻辑运算（与或非）
   - "timing_control"：包含定时/延时控制
   - "statistical_analysis"：包含统计计算（平均/最大/最小）
   - "variable_input"：主要涉及数据输入/输出
   - "general_query"：无法归类的通用查询

4. **detected_operations**：检测到的运算类型列表
   - 从以下枚举值中选取：["加法", "减法", "乘法", "除法", "模运算", "幂运算"]
   - 仅当需求中包含对应的数学运算时才列入
   - 没有数学运算时返回空列表

5. **keywords**：提取的领域术语和关键词列表

【约束】
- 输出必须是严格的 JSON 格式，不要输出任何额外解释文字
- intent 必须使用上述枚举值，不能自定义
- detected_operations 必须使用上述枚举值"""

        user_template = """用户需求：{query}

请分析并输出 JSON：
{{
  "queries": ["查询变体1", "查询变体2", "..."],
  "category_l1": "一级分类或空字符串",
  "intent": "意图枚举值",
  "detected_operations": ["运算1", "运算2"],
  "keywords": ["关键词1", "关键词2"]
}}"""

        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template),
        ])

    # ==================== LLM 意图分析核心方法 ====================

    @staticmethod
    def _extract_json_text(content: str) -> str:
        """从 LLM 输出中提取 JSON 文本"""
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if json_match:
            return json_match.group(1).strip()

        obj_match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
        if obj_match:
            return obj_match.group(1).strip()

        return content.strip()

    def _llm_analyze_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        调用 LLM 进行意图推断和查询变体生成

        Args:
            query: 用户原始需求文本

        Returns:
            分析结果字典，包含 queries/category_l1/intent/detected_operations/keywords
            LLM 调用失败时返回 None
        """
        # 缓存命中
        cached = self._analyze_cache.get(query)
        if cached is not None:
            return cached

        llm = self._ensure_llm()
        if llm is None:
            return None

        messages = self._analyze_prompt.format_messages(
            query=query,
            max_queries=config.RETRIEVAL_LLM_MAX_QUERIES,
        )

        start = time.perf_counter()
        try:
            response = llm.invoke(messages)
            raw = self._extract_json_text(getattr(response, "content", "") or "")
            plan = json.loads(raw) if raw else {}
            elapsed = (time.perf_counter() - start) * 1000
            if config.DEBUG:
                print(f"   🤖 LLM 意图分析完成 ({elapsed:.0f}ms)")
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            if config.DEBUG:
                print(f"   ⚠️  LLM 意图分析失败 ({elapsed:.0f}ms): {e}")
            return None

        if not isinstance(plan, dict):
            return None

        # 标准化 queries
        raw_queries = plan.get("queries", [])
        if not isinstance(raw_queries, list):
            raw_queries = []
        queries = [q.strip() for q in raw_queries
                   if isinstance(q, str) and q.strip()][:config.RETRIEVAL_LLM_MAX_QUERIES]

        # 标准化 intent（确保是合法枚举值）
        valid_intents = {
            "mathematical_computation", "comparison", "logic_operation",
            "timing_control", "statistical_analysis", "variable_input",
            "general_query"
        }
        raw_intent = (plan.get("intent", "") or "").strip()
        intent = raw_intent if raw_intent in valid_intents else "general_query"

        # 标准化 detected_operations（确保是合法枚举值）
        valid_operations = {"加法", "减法", "乘法", "除法", "模运算", "幂运算"}
        raw_ops = plan.get("detected_operations", [])
        if not isinstance(raw_ops, list):
            raw_ops = []
        detected_operations = [op for op in raw_ops
                               if isinstance(op, str) and op in valid_operations]

        # 标准化 category_l1
        category_l1 = (plan.get("category_l1", "") or "").strip()

        # 标准化 keywords
        raw_keywords = plan.get("keywords", [])
        if not isinstance(raw_keywords, list):
            raw_keywords = []
        keywords = [k for k in raw_keywords if isinstance(k, str) and k.strip()]

        result = {
            "queries": queries,
            "category_l1": category_l1,
            "intent": intent,
            "detected_operations": detected_operations,
            "keywords": keywords,
        }

        # 写入缓存
        self._analyze_cache[query] = result

        if config.DEBUG:
            print(f"   📋 意图: {intent}")
            if detected_operations:
                print(f"   🔧 检测到运算: {', '.join(detected_operations)}")
            print(f"   📝 生成 {len(queries)} 个查询变体")
            for i, q in enumerate(queries, 1):
                print(f"      [{i}] {q}")

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

    # ==================== 知识库管理 ====================

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

    # ==================== 检索主方法 ====================

    def retrieve(self, query: str, top_k: int = 10,
                 category_filter: Optional[str] = None,
                 similarity_threshold: float = 0.3,
                 ) -> Dict[str, Any]:
        """
        检索相关知识（LLM 驱动）

        流程：
          1. 调用 LLM 进行意图推断和查询变体生成
          2. 根据 LLM 结果走批量多查询或单查询检索
          3. LLM 不可用时兜底：使用原始查询做单次检索

        Args:
            query: 用户查询/需求
            top_k: 返回的最相关文档数量
            category_filter: 可选的类别过滤（如 "逻辑模块"）
            similarity_threshold: 相似度阈值，低于此值的结果将被过滤

        Returns:
            包含上下文信息的字典（与旧版结构完全一致）
        """
        if config.DEBUG:
            print(f"\n🔍 开始检索: {query}")
            print(f"   Top-K: {top_k}, 类别过滤: {category_filter or '无'}")

        # ========== 第1步：LLM 意图分析与查询生成 ==========
        analysis = self._llm_analyze_query(query)
        llm_succeeded = analysis is not None and len(analysis.get("queries", [])) > 0

        # ========== 第2步：category_l1 过滤 ==========
        if llm_succeeded and not category_filter:
            llm_category_l1 = analysis.get("category_l1", "")
            allowed_prefixes = {
                "逻辑模块", "运算模块", "变量模块", "定时模块",
                "累计模块", "应用", "基础组件", "高级组件", "备注组件", "其他",
            }
            if llm_category_l1 in allowed_prefixes:
                category_filter = llm_category_l1
                if config.DEBUG:
                    print(f"   🏷️  LLM 推断类别过滤: {category_filter}")

        # ========== 第3步：执行检索 ==========
        if llm_succeeded:
            enhanced = {
                "original_query": query,
                "query_variants": analysis["queries"],
                "detected_operations": analysis.get("detected_operations", []),
                "intent": analysis.get("intent", "general_query"),
            }

            if config.DEBUG:
                print(f"   🔧 检测到运算: {', '.join(enhanced['detected_operations'])}" if enhanced['detected_operations'] else "")

            context = self._multi_query_retrieve(
                enhanced, top_k, category_filter, similarity_threshold
            )
        else:
            if config.DEBUG:
                print(f"   ⚡ 使用兜底策略: 原始查询单次检索")
            context = self._single_query_retrieve(
                query, top_k, category_filter, similarity_threshold
            )

        # ========== 第4步：增强元数据（保持与旧版兼容） ==========
        meta = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
        meta = dict(meta)
        meta["rewrite_used"] = llm_succeeded
        if llm_succeeded:
            meta["llm_queries"] = analysis.get("queries", [])
            meta["llm_category_l1"] = analysis.get("category_l1", "")
        context["metadata"] = meta

        return context

    # ==================== 单查询检索 ====================

    def _single_query_retrieve(self, query: str, top_k: int,
                               category_filter: Optional[str],
                               similarity_threshold: float) -> Dict[str, Any]:
        """
        单查询检索（兜底方法）

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
            
            if results and results['documents'] and len(results['documents'][0]) > 0:
                documents = results['documents'][0]
                metadatas = results['metadatas'][0]
                distances = results['distances'][0] if 'distances' in results else [0] * len(documents)
                
                for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
                    similarity_score = self._normalize_distance(distance)
                    
                    if similarity_score < similarity_threshold:
                        if config.DEBUG:
                            print(f"   ⚠️  过滤低分结果: {metadata.get('module_type')} (分数: {similarity_score:.3f})")
                        continue
                    
                    try:
                        module_schema = json.loads(metadata.get('json_schema', '{}'))
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
                        
                        if config.DEBUG:
                            print(f"   ✅ 匹配 #{i+1}: {metadata.get('module_type')} "
                                  f"({node_info['name']}) - 分数: {similarity_score:.3f}")
                    
                    except json.JSONDecodeError as e:
                        if config.DEBUG:
                            print(f"   ❌ JSON 解析错误: {e}")
                        continue
            
            context = {
                "query": query,
                "relevant_nodes": relevant_nodes,
                "similar_cases": [],
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

    # ==================== 多查询检索 ====================

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
            # ====== 核心：单次批量向量检索 ======
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
                    
                    if similarity_score < similarity_threshold:
                        if config.DEBUG:
                            print(f"   ⚠️  过滤低分结果: {metadata.get('module_type')} "
                                  f"(分数: {similarity_score:.3f}, 来源: 变体#{variant_idx+1})")
                        continue
                    
                    module_type = metadata.get('module_type')
                    
                    if (module_type in all_results
                            and similarity_score <= all_results[module_type]['similarity_score']):
                        continue
                    
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
                        "rank": 0,
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
        
        sorted_nodes = sorted(
            all_results.values(),
            key=lambda x: x['similarity_score'],
            reverse=True
        )[:top_k]
        
        for i, node in enumerate(sorted_nodes):
            node['rank'] = i + 1
        
        if config.DEBUG:
            print(f"   🎯 批量多查询合并完成: 找到 {len(sorted_nodes)} 个相关模块")
        
        return {
            "query": enhanced['original_query'],
            "relevant_nodes": sorted_nodes,
            "similar_cases": [],
            "metadata": {
                "retrieved_count": len(sorted_nodes),
                "query_variants_used": len(query_variants),
                "detected_operations": enhanced['detected_operations'],
                "intent": enhanced['intent'],
                "avg_confidence_score": sum(n['similarity_score'] for n in sorted_nodes) / len(sorted_nodes) if sorted_nodes else 0
            }
        }

    # ==================== 示例代码生成 ====================

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

    # ==================== 知识库加载 ====================

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

    # ==================== LangGraph 节点接口 ====================

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
