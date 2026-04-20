"""
检索智能体 (Retrieval Agent)
职责：消费 Analysis Agent 生成的检索计划，并从向量数据库中检索相关领域知识。
"""
from typing import Dict, List, Any, Optional
import json
import os
import chromadb
import config
from utils.console_utils import safe_print as print
from utils.model_manager import EmbeddingManager
from utils.retrieval_bundle_utils import (
    load_structured_payload,
)


class RetrievalAgent:
    """检索智能体（纯检索执行器）"""

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
            llm_provider: 为兼容旧调用保留，当前未使用
            llm_model: 为兼容旧调用保留，当前未使用
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

        self.atomic_collection_name = getattr(config, "CHROMA_COLLECTION_ATOMIC_MODULES", "kong_modules_v1")
        self.subflow_collection_name = getattr(config, "CHROMA_COLLECTION_SUBFLOW_TEMPLATES", "ahu_subflow_templates_v1")
        self.system_pattern_collection_name = getattr(config, "CHROMA_COLLECTION_SYSTEM_PATTERNS", "ahu_system_patterns_v1")

        self.atomic_collection = self._get_collection(
            self.atomic_collection_name,
            create_if_missing=True,
            description="KONG CUBE 模块知识库",
        )
        self.collection = self.atomic_collection
        self.subflow_collection = self._get_collection(self.subflow_collection_name, create_if_missing=False)
        self.system_pattern_collection = self._get_collection(self.system_pattern_collection_name, create_if_missing=False)

    @staticmethod
    def _clean_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    @classmethod
    def _clean_text_list(cls, value: Any, max_items: Optional[int] = None) -> List[str]:
        if not isinstance(value, list):
            return []

        result = []
        for item in value:
            text = cls._clean_text(item)
            if text:
                result.append(text)

        if max_items is not None:
            return result[:max_items]
        return result

    @classmethod
    def _top_asset_identifiers(
        cls,
        items: Any,
        *candidate_keys: str,
        limit: int = 5,
    ) -> List[str]:
        if not isinstance(items, list):
            return []

        ordered: List[str] = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            identifier = ""
            for key in candidate_keys:
                identifier = cls._clean_text(item.get(key))
                if identifier:
                    break
            if identifier and identifier not in seen:
                ordered.append(identifier)
                seen.add(identifier)
            if len(ordered) >= limit:
                break
        return ordered

    @staticmethod
    def _top_asset_scores(items: Any, limit: int = 5) -> List[float]:
        if not isinstance(items, list):
            return []

        scores: List[float] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                scores.append(0.0)
                continue
            try:
                scores.append(round(float(item.get("similarity_score", 0.0) or 0.0), 4))
            except (TypeError, ValueError):
                scores.append(0.0)
        return scores

    def _normalize_retrieval_plan(self, retrieval_plan: Any, query: str) -> Dict[str, Any]:
        if not isinstance(retrieval_plan, dict):
            retrieval_plan = {}

        queries = self._clean_text_list(
            retrieval_plan.get("queries", []),
            config.RETRIEVAL_LLM_MAX_QUERIES,
        )

        valid_intents = {
            "mathematical_computation", "comparison", "logic_operation",
            "timing_control", "statistical_analysis", "variable_input",
            "general_query",
        }
        raw_intent = self._clean_text(retrieval_plan.get("intent", ""))
        intent = raw_intent if raw_intent in valid_intents else "general_query"

        valid_operations = {"加法", "减法", "乘法", "除法", "模运算", "幂运算"}
        raw_ops = retrieval_plan.get("detected_operations", [])
        if not isinstance(raw_ops, list):
            raw_ops = []
        detected_operations = [op for op in raw_ops if isinstance(op, str) and op in valid_operations]

        return {
            "queries": queries,
            "category_l1": self._clean_text(retrieval_plan.get("category_l1", "")),
            "intent": intent,
            "detected_operations": detected_operations,
            "keywords": self._clean_text_list(retrieval_plan.get("keywords", [])),
            "original_query": query,
        }

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

    def _get_collection(
        self,
        name: str,
        create_if_missing: bool = False,
        description: str = "",
    ):
        try:
            collection = self.client.get_collection(
                name=name,
                embedding_function=self.embedding_function,
            )
            if config.DEBUG:
                print(f"✅ 已加载知识库集合 {name}，包含 {collection.count()} 条记录")
            return collection
        except Exception:
            if not create_if_missing:
                if config.DEBUG:
                    print(f"ℹ️  知识库集合 {name} 不存在，Phase 2 对应切片将返回空结果")
                return None

        collection = self.client.create_collection(
            name=name,
            embedding_function=self.embedding_function,
            metadata={"description": description or name},
        )
        if config.DEBUG:
            print(f"📦 创建新的知识库集合 {name}")
        return collection

    def _build_scenario_queries(self, scenario_analysis: Dict[str, Any], fields: List[str], fallback_query: str) -> List[str]:
        queries: List[str] = []
        if not isinstance(scenario_analysis, dict):
            scenario_analysis = {}

        for field in fields:
            value = scenario_analysis.get(field)
            if isinstance(value, str):
                text = self._clean_text(value)
                if text:
                    queries.append(text)
            elif isinstance(value, list):
                cleaned = self._clean_text_list(value, 5)
                queries.extend(cleaned)
                if cleaned:
                    queries.append(" ".join(cleaned[:3]))

        high_value_fields = [
            self._clean_text(str(scenario_analysis.get(key, "")))
            for key in ("system_type", "business_goal", "equipment_object", "actuator", "control_strategy", "output_signal")
            if self._clean_text(str(scenario_analysis.get(key, "")))
        ]
        if high_value_fields:
            queries.append(" ".join(high_value_fields[:4]))

        deduped = []
        seen = set()
        for item in queries + [fallback_query]:
            cleaned = self._clean_text(item)
            if cleaned and cleaned not in seen:
                deduped.append(cleaned)
                seen.add(cleaned)
        return deduped[: config.RETRIEVAL_LLM_MAX_QUERIES]

    def _query_asset_collection(
        self,
        collection,
        query_variants: List[str],
        top_k: int,
        similarity_threshold: float,
        asset_type: str,
    ) -> List[Dict[str, Any]]:
        if collection is None or not query_variants:
            return []

        merged = {}
        try:
            results = collection.query(
                query_texts=query_variants,
                n_results=min(top_k, 5),
            )
        except Exception as exc:
            if config.DEBUG:
                print(f"   ⚠️ 查询 {asset_type} 集合失败: {exc}")
            return []

        for variant_index, variant in enumerate(query_variants):
            if not results or not results.get('metadatas') or variant_index >= len(results['metadatas']):
                continue
            metadatas = results['metadatas'][variant_index]
            distances = results.get('distances', [])
            distances = distances[variant_index] if variant_index < len(distances) else [0] * len(metadatas)

            for rank, (metadata, distance) in enumerate(zip(metadatas, distances), start=1):
                similarity_score = self._normalize_distance(distance)
                if similarity_score < similarity_threshold:
                    continue

                payload = load_structured_payload(metadata)
                if not payload:
                    continue

                lookup_key = self._clean_text(
                    str(
                        payload.get('module_type')
                        or payload.get('pattern_id')
                        or payload.get('template_id')
                        or payload.get('definition_id')
                        or metadata.get('module_type')
                        or metadata.get('pattern_id')
                        or ''
                    )
                )
                if not lookup_key:
                    continue

                existing = merged.get(lookup_key)
                if existing and similarity_score <= existing.get('similarity_score', 0):
                    continue

                item = dict(payload)
                item.setdefault('asset_type', asset_type)
                item['similarity_score'] = similarity_score
                item['rank'] = rank
                item['matched_query'] = variant
                merged[lookup_key] = item

        ranked = sorted(merged.values(), key=lambda item: item.get('similarity_score', 0), reverse=True)[:top_k]
        for index, item in enumerate(ranked, start=1):
            item['rank'] = index
        return ranked

    # ==================== 检索主方法 ====================

    def _retrieve_atomic_context(self, query: str, top_k: int = 10,
                 category_filter: Optional[str] = None,
                 similarity_threshold: float = 0.3,
                 analysis_result: Optional[Dict[str, Any]] = None,
                 ) -> Dict[str, Any]:
        """
                检索相关知识

        流程：
                    1. 读取分析智能体提供的检索计划
                    2. 根据检索计划走批量多查询或单查询检索
                    3. 检索计划不可用时兜底：使用原始查询做单次检索

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

        retrieval_plan = self._normalize_retrieval_plan(
            (analysis_result or {}).get("retrieval_plan", {}),
            query,
        )
        analysis_available = len(retrieval_plan.get("queries", [])) > 0
        scenario_analysis = (analysis_result or {}).get("scenario_analysis", {})

        # ========== 第2步：category_l1 过滤 ==========
        if analysis_available and not category_filter:
            llm_category_l1 = retrieval_plan.get("category_l1", "")
            allowed_prefixes = {
                "逻辑模块", "运算模块", "变量模块", "定时模块",
                "累计模块", "应用", "基础组件", "高级组件", "备注组件", "其他",
            }
            if llm_category_l1 in allowed_prefixes:
                category_filter = llm_category_l1
                if config.DEBUG:
                    print(f"   🏷️  LLM 推断类别过滤: {category_filter}")

        # ========== 第3步：执行检索 ==========
        if analysis_available:
            enhanced = {
                "original_query": query,
                "query_variants": retrieval_plan["queries"],
                "detected_operations": retrieval_plan.get("detected_operations", []),
                "intent": retrieval_plan.get("intent", "general_query"),
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
        meta["rewrite_used"] = analysis_available
        meta["analysis_used"] = bool(analysis_result)
        if analysis_available:
            meta["llm_queries"] = retrieval_plan.get("queries", [])
            meta["llm_category_l1"] = retrieval_plan.get("category_l1", "")
        if isinstance(scenario_analysis, dict):
            meta["analysis_summary"] = self._clean_text(scenario_analysis.get("summary", ""))
            try:
                meta["analysis_confidence"] = float(scenario_analysis.get("confidence", 0.0))
            except (TypeError, ValueError):
                meta["analysis_confidence"] = 0.0
        context["metadata"] = meta

        return context

    def retrieve_bundle(
        self,
        query: str,
        top_k: int = 10,
        category_filter: Optional[str] = None,
        similarity_threshold: float = 0.3,
        analysis_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        retrieval_plan = self._normalize_retrieval_plan(
            (analysis_result or {}).get("retrieval_plan", {}),
            query,
        )
        scenario_analysis = (analysis_result or {}).get("scenario_analysis", {})
        atomic_context = self._retrieve_atomic_context(
            query=query,
            top_k=top_k,
            category_filter=category_filter,
            similarity_threshold=similarity_threshold,
            analysis_result=analysis_result,
        )

        subflow_templates = self._query_asset_collection(
            self.subflow_collection,
            self._build_scenario_queries(
                scenario_analysis,
                ["business_goal", "system_type", "equipment_object", "actuator", "control_strategy", "output_signal"],
                query,
            ),
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            asset_type="subflow_template",
        )
        system_patterns = self._query_asset_collection(
            self.system_pattern_collection,
            self._build_scenario_queries(
                scenario_analysis,
                ["system_type", "control_mode", "operating_conditions", "input_signals", "output_signals"],
                query,
            ),
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            asset_type="system_pattern",
        )

        selected_pattern = system_patterns[0] if system_patterns else {}
        style_guides = []
        if isinstance(selected_pattern.get("style_guides"), dict) and selected_pattern.get("style_guides"):
            style_guides.append(selected_pattern["style_guides"])

        atomic_metadata = atomic_context.get("metadata", {}) if isinstance(atomic_context.get("metadata"), dict) else {}
        llm_queries = self._clean_text_list(atomic_metadata.get("llm_queries", []), config.RETRIEVAL_LLM_MAX_QUERIES)
        query_variants = retrieval_plan.get("queries", []) or [query]
        analysis_summary = self._clean_text(atomic_metadata.get("analysis_summary", ""))
        llm_category_l1 = self._clean_text(atomic_metadata.get("llm_category_l1", ""))
        try:
            analysis_confidence = float(atomic_metadata.get("analysis_confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            analysis_confidence = 0.0

        return {
            "atomic_modules": atomic_context.get("relevant_nodes", []),
            "subflow_templates": subflow_templates,
            "system_patterns": system_patterns,
            "style_guides": style_guides,
            "metadata": {
                "query_text": query,
                "query_variants": query_variants,
                "intent": retrieval_plan.get("intent", "general_query"),
                "detected_operations": retrieval_plan.get("detected_operations", []),
                "selected_case_pattern_id": selected_pattern.get("pattern_id", ""),
                "retrieved_atomic_count": len(atomic_context.get("relevant_nodes", [])),
                "retrieved_subflow_count": len(subflow_templates),
                "retrieved_pattern_count": len(system_patterns),
                "avg_atomic_score": atomic_context.get("metadata", {}).get("avg_confidence_score", 0.0),
                "rewrite_used": bool(atomic_metadata.get("rewrite_used", False)),
                "analysis_used": bool(atomic_metadata.get("analysis_used", False)),
                "llm_queries": llm_queries,
                "llm_category_l1": llm_category_l1,
                "analysis_summary": analysis_summary,
                "analysis_confidence": analysis_confidence,
                "top_atomic_module_types": self._top_asset_identifiers(
                    atomic_context.get("relevant_nodes", []),
                    "module_type",
                    limit=5,
                ),
                "top_atomic_scores": self._top_asset_scores(atomic_context.get("relevant_nodes", []), limit=5),
                "top_subflow_template_ids": self._top_asset_identifiers(
                    subflow_templates,
                    "template_id",
                    "module_type",
                    limit=5,
                ),
                "top_subflow_scores": self._top_asset_scores(subflow_templates, limit=5),
                "top_system_pattern_ids": self._top_asset_identifiers(
                    system_patterns,
                    "pattern_id",
                    limit=5,
                ),
                "top_system_pattern_scores": self._top_asset_scores(system_patterns, limit=5),
                "query_bundle_version": "phase2-v1",
            },
        }

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
        analysis_result = state.get("analysis_result", {})

        bundle = self.retrieve_bundle(user_query, analysis_result=analysis_result)

        state["retrieval_bundle"] = bundle
        state["current_step"] = "retrieval_completed"

        return state
