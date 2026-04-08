"""
分析智能体 (Analysis Agent)
职责：理解暖通/楼控业务场景，产出检索计划与业务场景摘要。
"""
from typing import Any, Dict, List, Optional
import json
import re
import time

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

import config
from utils.console_utils import safe_print as print
from utils.model_manager import LLMManager
from utils.phase3_adapters import build_requirement_spec


class RetrievalPlan(BaseModel):
	"""提供给检索智能体的检索计划。"""

	queries: List[str] = Field(default_factory=list)
	category_l1: str = Field(default="")
	intent: str = Field(default="general_query")
	detected_operations: List[str] = Field(default_factory=list)
	keywords: List[str] = Field(default_factory=list)


class ScenarioAnalysis(BaseModel):
	"""面向规划智能体的业务场景分析。"""

	summary: str = Field(default="")
	business_goal: str = Field(default="")
	system_type: str = Field(default="")
	equipment_object: str = Field(default="")
	actuator: str = Field(default="")
	controlled_variable: str = Field(default="")
	feedback_variable: str = Field(default="")
	setpoint_variable: str = Field(default="")
	output_signal: str = Field(default="")
	control_strategy: str = Field(default="")
	control_mode: str = Field(default="")
	input_signals: List[str] = Field(default_factory=list)
	output_signals: List[str] = Field(default_factory=list)
	operating_conditions: List[str] = Field(default_factory=list)
	interlocks_or_limits: List[str] = Field(default_factory=list)
	calculation_logic: List[str] = Field(default_factory=list)
	ambiguities: List[str] = Field(default_factory=list)
	assumptions: List[str] = Field(default_factory=list)
	confidence: float = Field(default=0.0)


class AnalysisMetadata(BaseModel):
	"""分析元数据。"""

	llm_used: bool = Field(default=False)
	cached: bool = Field(default=False)
	fallback_used: bool = Field(default=False)


class AnalysisResult(BaseModel):
	"""分析智能体统一输出。"""

	retrieval_plan: RetrievalPlan = Field(default_factory=RetrievalPlan)
	scenario_analysis: ScenarioAnalysis = Field(default_factory=ScenarioAnalysis)
	metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)


class AnalysisAgent:
	"""分析智能体。"""

	def __init__(self, llm_provider: Optional[str] = None, llm_model: Optional[str] = None):
		provider = llm_provider or config.ANALYSIS_LLM_PROVIDER or config.LLM_PROVIDER
		model_name = llm_model or config.ANALYSIS_LLM_MODEL or None

		self.llm = LLMManager.get_llm(
			provider,
			model=model_name,
			temperature=config.ANALYSIS_LLM_TEMPERATURE,
			timeout=config.ANALYSIS_LLM_TIMEOUT_S,
		)
		self.prompt = self._create_prompt()
		self._analyze_cache: Dict[str, Dict[str, Any]] = {}

		if config.DEBUG:
			print("✅ 分析智能体初始化完成")
			print(f"   LLM 提供商: {provider}")
			print(f"   温度: {config.ANALYSIS_LLM_TEMPERATURE}")
			if model_name:
				print(f"   指定模型: {model_name}")

	def _create_prompt(self) -> ChatPromptTemplate:
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
- detected_operations 必须使用上述枚举值

在保持上述 retrieval_plan 分析规则完全不变的前提下，你还需要额外输出 scenario_analysis，用于给规划智能体提供暖通/楼控业务场景参考。

【scenario_analysis 生成要求】
请尽量抽取以下业务槽位：
- business_goal：业务目标
- system_type：系统类型，如 AHU、冷冻水系统等
- equipment_object：设备对象或控制对象
- actuator：执行器
- controlled_variable：被控量
- feedback_variable：反馈量
- setpoint_variable：设定值
- output_signal：控制输出或目标输出
- control_strategy：控制策略，如 PID、回差控制、联锁、启停等
- control_mode：模式信息，如制冷/制热、自动/手动
- input_signals、output_signals、operating_conditions、interlocks_or_limits、calculation_logic
- ambiguities：关键模糊点
- assumptions：保守假设

【额外约束】
- 不得编造用户没有明确给出的业务事实；无法确定时留空，或放入 ambiguities / assumptions
- summary 必须是简短摘要，聚焦规划所需信息"""

		user_template = """用户需求：{query}

请分析并输出 JSON，其中 retrieval_plan 部分必须遵循以下结构：
{{
  "retrieval_plan": {{
	 "queries": ["查询变体1", "查询变体2", "..."],
	 "category_l1": "一级分类或空字符串",
	 "intent": "意图枚举值",
	 "detected_operations": ["运算1", "运算2"],
	 "keywords": ["关键词1", "关键词2"]
  }},
  "scenario_analysis": {{
	 "summary": "面向规划智能体的业务摘要",
	 "business_goal": "",
	 "system_type": "",
	 "equipment_object": "",
	 "actuator": "",
	 "controlled_variable": "",
	 "feedback_variable": "",
	 "setpoint_variable": "",
	 "output_signal": "",
	 "control_strategy": "",
	 "control_mode": "",
	 "input_signals": [],
	 "output_signals": [],
	 "operating_conditions": [],
	 "interlocks_or_limits": [],
	 "calculation_logic": [],
	 "ambiguities": [],
	 "assumptions": [],
	 "confidence": 0.0
  }}
}}"""

		return ChatPromptTemplate.from_messages([
			("system", system_prompt),
			("user", user_template),
		])

	@staticmethod
	def _extract_json_text(content: str) -> str:
		json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
		if json_match:
			return json_match.group(1).strip()

		obj_match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
		if obj_match:
			return obj_match.group(1).strip()

		return content.strip()

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

	def _normalize_retrieval_plan(self, payload: Dict[str, Any], query: str) -> Dict[str, Any]:
		raw_queries = payload.get("queries", [])
		queries = self._clean_text_list(raw_queries, config.RETRIEVAL_LLM_MAX_QUERIES)

		valid_intents = {
			"mathematical_computation", "comparison", "logic_operation",
			"timing_control", "statistical_analysis", "variable_input",
			"general_query",
		}
		raw_intent = self._clean_text(payload.get("intent", ""))
		intent = raw_intent if raw_intent in valid_intents else "general_query"

		valid_operations = {"加法", "减法", "乘法", "除法", "模运算", "幂运算"}
		raw_ops = payload.get("detected_operations", [])
		if not isinstance(raw_ops, list):
			raw_ops = []
		detected_operations = [op for op in raw_ops if isinstance(op, str) and op in valid_operations]

		category_l1 = self._clean_text(payload.get("category_l1", ""))
		keywords = self._clean_text_list(payload.get("keywords", []))

		if not queries and query.strip():
			queries = [query.strip()]

		return {
			"queries": queries,
			"category_l1": category_l1,
			"intent": intent,
			"detected_operations": detected_operations,
			"keywords": keywords,
		}

	def _normalize_scenario_analysis(self, payload: Dict[str, Any], query: str) -> Dict[str, Any]:
		if not isinstance(payload, dict):
			payload = {}

		summary = self._clean_text(payload.get("summary", ""))
		if not summary:
			summary = query.strip()[:120]
		if len(summary) > 120:
			summary = summary[:120]

		confidence = payload.get("confidence", 0.0)
		try:
			confidence = float(confidence)
		except (TypeError, ValueError):
			confidence = 0.0
		confidence = max(0.0, min(1.0, confidence))

		return {
			"summary": summary,
			"business_goal": self._clean_text(payload.get("business_goal", "")),
			"system_type": self._clean_text(payload.get("system_type", "")),
			"equipment_object": self._clean_text(payload.get("equipment_object", "")),
			"actuator": self._clean_text(payload.get("actuator", "")),
			"controlled_variable": self._clean_text(payload.get("controlled_variable", "")),
			"feedback_variable": self._clean_text(payload.get("feedback_variable", "")),
			"setpoint_variable": self._clean_text(payload.get("setpoint_variable", "")),
			"output_signal": self._clean_text(payload.get("output_signal", "")),
			"control_strategy": self._clean_text(payload.get("control_strategy", "")),
			"control_mode": self._clean_text(payload.get("control_mode", "")),
			"input_signals": self._clean_text_list(payload.get("input_signals", [])),
			"output_signals": self._clean_text_list(payload.get("output_signals", [])),
			"operating_conditions": self._clean_text_list(payload.get("operating_conditions", [])),
			"interlocks_or_limits": self._clean_text_list(payload.get("interlocks_or_limits", [])),
			"calculation_logic": self._clean_text_list(payload.get("calculation_logic", [])),
			"ambiguities": self._clean_text_list(payload.get("ambiguities", []), config.ANALYSIS_MAX_AMBIGUITIES),
			"assumptions": self._clean_text_list(payload.get("assumptions", []), config.ANALYSIS_MAX_ASSUMPTIONS),
			"confidence": confidence,
		}

	def _fallback_result(self, query: str, cached: bool = False) -> Dict[str, Any]:
		return {
			"retrieval_plan": {
				"queries": [query.strip()] if query.strip() else [],
				"category_l1": "",
				"intent": "general_query",
				"detected_operations": [],
				"keywords": [],
			},
			"scenario_analysis": {
				"summary": query.strip()[:120],
				"business_goal": "",
				"system_type": "",
				"equipment_object": "",
				"actuator": "",
				"controlled_variable": "",
				"feedback_variable": "",
				"setpoint_variable": "",
				"output_signal": "",
				"control_strategy": "",
				"control_mode": "",
				"input_signals": [],
				"output_signals": [],
				"operating_conditions": [],
				"interlocks_or_limits": [],
				"calculation_logic": [],
				"ambiguities": ["分析智能体未能完成结构化场景解析"],
				"assumptions": [],
				"confidence": 0.0,
			},
			"metadata": {
				"llm_used": False,
				"cached": cached,
				"fallback_used": True,
			},
		}

	def analyze(self, query: str) -> Dict[str, Any]:
		cached = self._analyze_cache.get(query)
		if cached is not None:
			result = dict(cached)
			result["metadata"] = dict(result.get("metadata", {}))
			result["metadata"]["cached"] = True
			return result

		messages = self.prompt.format_messages(
			query=query,
			max_queries=config.RETRIEVAL_LLM_MAX_QUERIES,
		)

		start = time.perf_counter()
		try:
			# 对 OpenAI 兼容提供商（Qwen/DeepSeek/Kimi 等），function_calling
			# 比默认的 response_format/json_schema 兼容性更稳定。
			structured_llm = self.llm.with_structured_output(
				AnalysisResult,
				method="function_calling",
			)
			response = structured_llm.invoke(messages)
			raw_result = response.model_dump()
			llm_used = True
			fallback_used = False
			if config.DEBUG:
				elapsed = (time.perf_counter() - start) * 1000
				print(f"   🤖 分析智能体 Structured Output 完成 ({elapsed:.0f}ms)")
		except Exception as structured_error:
			try:
				response = self.llm.invoke(messages)
				raw = self._extract_json_text(getattr(response, "content", "") or "")
				raw_result = json.loads(raw) if raw else {}
				llm_used = True
				fallback_used = False
				if config.DEBUG:
					elapsed = (time.perf_counter() - start) * 1000
					print(f"   ⚠️ Structured Output 失败，已回退 JSON 解析 ({elapsed:.0f}ms): {structured_error}")
			except Exception as parse_error:
				if config.DEBUG:
					elapsed = (time.perf_counter() - start) * 1000
					print(f"   ⚠️ 分析智能体失败，使用本地兜底 ({elapsed:.0f}ms): {parse_error}")
				result = self._fallback_result(query)
				self._analyze_cache[query] = result
				return result

		if not isinstance(raw_result, dict):
			result = self._fallback_result(query)
			self._analyze_cache[query] = result
			return result

		retrieval_plan = self._normalize_retrieval_plan(raw_result.get("retrieval_plan", {}), query)
		scenario_analysis = self._normalize_scenario_analysis(raw_result.get("scenario_analysis", {}), query)

		result = {
			"retrieval_plan": retrieval_plan,
			"scenario_analysis": scenario_analysis,
			"metadata": {
				"llm_used": llm_used,
				"cached": False,
				"fallback_used": fallback_used,
			},
		}

		self._analyze_cache[query] = result
		return result

	def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
		user_query = state.get("user_query", "")
		analysis_result = self.analyze(user_query)
		state["analysis_result"] = analysis_result
		state["requirement_spec"] = build_requirement_spec(analysis_result)
		state["current_step"] = "analysis_completed"
		return state
